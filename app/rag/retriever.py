"""Hybrid semantic and lexical document retrieval with graceful degradation."""
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from app.rag.lexical_store import search_chunks
from app.rag.vector_store import get_vector_store

logger = logging.getLogger("stockrag.rag")


def _citation(metadata: dict) -> str:
    if str(metadata.get("source_type", "")).casefold() in {"sec", "sec_filing", "official_filing"}:
        filing_type = metadata.get("document_type") or "SEC filing"
        ticker = metadata.get("ticker")
        filing_label = " ".join(str(value) for value in (ticker, filing_type) if value)
        url = metadata.get("source_url") or metadata.get("url")
        label = f"SEC {filing_label}".strip()
        return f"{label} — {url}" if url else label
    source_name = metadata.get("title") or metadata.get("source") or metadata.get("filename") or "Unknown"
    if metadata.get("document_type") == "pdf" or str(metadata.get("filename", "")).casefold().endswith(".pdf"):
        return f"{source_name} — Page {metadata.get('page', '?')}"
    if metadata.get("document_type") == "web" or metadata.get("source_type") == "web":
        return f"{source_name}\n   {metadata.get('source_url') or metadata.get('url') or 'Unknown URL'}"
    if metadata.get("section"):
        return f"{source_name} — {metadata['section']}"
    return str(source_name)


def _where_filter(metadata_filter: dict | None) -> dict | None:
    if not metadata_filter:
        return None
    clauses = []
    for field, value in metadata_filter.items():
        if value is None:
            continue
        clauses.append({field: value})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses} if clauses else None


def _recency_boost(metadata: dict) -> float:
    value = metadata.get("filing_date") or metadata.get("published_at") or metadata.get("updated_at")
    if not value:
        return 0.0
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            stamp = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, OverflowError):
            return 0.0
    try:
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age_days = max(0, (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).days)
        return 0.03 * (2 ** (-age_days / 365))
    except (TypeError, ValueError):
        return 0.0


def retrieve_context(query: str, k: int = 5, document_ids: list[int] | None = None, metadata_filter: dict | None = None):
    """Return hybrid evidence, degrading to durable FTS retrieval when FAISS is unavailable."""
    semantic_results = []
    semantic_error = None
    try:
        vector_store = get_vector_store()
        filters = dict(metadata_filter or {})
        if document_ids:
            filters["document_id"] = {"$in": document_ids}
        semantic_results = vector_store.similarity_search_with_score(query, k=max(k * 3, k), filter=_where_filter(filters))
    except Exception as exc:
        semantic_error = str(exc)
        logger.warning("rag_semantic_retrieval_unavailable", extra={"reason": semantic_error})

    lexical_results = []
    lexical_error = None
    try:
        lexical_results = search_chunks(query, k=max(k * 3, k), document_ids=document_ids, metadata_filter=metadata_filter)
    except Exception as exc:
        lexical_error = str(exc)
        logger.exception("rag_lexical_retrieval_failed", extra={"reason": lexical_error})

    fused: dict[tuple[str, str], dict] = {}
    for rank, (doc, _score) in enumerate(semantic_results, start=1):
        metadata = doc.metadata or {}
        key = (doc.page_content, str(metadata.get("document_id", "")))
        entry = fused.setdefault(key, {"content": doc.page_content, "metadata": metadata, "score": 0.0})
        entry["score"] += 1 / (60 + rank)
    for rank, row in enumerate(lexical_results, start=1):
        metadata = {key: row.get(key) for key in ("source", "filename", "document_id", "page", "document_type", "url", "title", "company", "ticker", "exchange", "country", "sector", "industry", "source_type", "source_url", "published_at", "filing_date", "period_start", "period_end", "chunk_id", "chunk_index", "content_hash", "created_at", "updated_at")}
        key = (row["content"], str(row.get("document_id", "")))
        entry = fused.setdefault(key, {"content": row["content"], "metadata": metadata, "score": 0.0})
        entry["score"] += 1 / (60 + rank)
    for entry in fused.values():
        metadata = entry["metadata"]
        if metadata_filter and metadata.get("ticker") and str(metadata.get("ticker")).casefold() == str(metadata_filter.get("ticker", "")).casefold():
            entry["score"] += 0.1
        if str(metadata.get("source_type", "")).casefold() in {"sec", "sec_filing", "official_filing"}:
            entry["score"] += 0.01
        entry["score"] += _recency_boost(metadata)
    merged = sorted(fused.values(), key=lambda entry: entry["score"], reverse=True)[:k]

    context_parts = [entry["content"] for entry in merged]
    sources = list(dict.fromkeys(_citation(entry["metadata"]) for entry in merged))
    mode = "hybrid" if semantic_results and lexical_results else "semantic" if semantic_results else "keyword" if lexical_results else "unavailable"
    result = {
        "context": "\n\n---\n\n".join(context_parts),
        "sources": sources,
        "passages": [{"content": entry["content"], "source": _citation(entry["metadata"]), "score": entry["score"], "metadata": entry["metadata"]} for entry in merged],
        "retrieval_mode": mode,
        "degraded": mode == "keyword",
    }
    if not merged and semantic_error and lexical_error:
        result["error"] = "Document search is unavailable: both semantic and keyword retrieval failed."
    return result
