"""Hybrid semantic and lexical document retrieval with graceful degradation."""
import logging
from types import SimpleNamespace

from app.rag.lexical_store import search_chunks
from app.rag.vector_store import get_vector_store

logger = logging.getLogger("stockrag.rag")


def _citation(metadata: dict) -> str:
    source_name = metadata.get("source") or metadata.get("filename") or "Unknown"
    if metadata.get("document_type") == "pdf":
        return f"{source_name} — Page {metadata.get('page', '?')}"
    if metadata.get("document_type") == "web":
        return f"{source_name}\n   {metadata.get('url') or 'Unknown URL'}"
    return str(source_name)


def retrieve_context(query: str, k: int = 5, document_ids: list[int] | None = None):
    """Return relevant context; use durable FTS retrieval if Chroma is unavailable."""
    semantic_results = []
    semantic_error = None
    try:
        vector_store = get_vector_store()
        metadata_filter = {"document_id": {"$in": document_ids}} if document_ids else None
        semantic_results = vector_store.similarity_search_with_score(query, k=k, filter=metadata_filter)
    except Exception as exc:
        semantic_error = str(exc)
        logger.warning("rag_semantic_retrieval_unavailable", extra={"reason": semantic_error})

    lexical_results = []
    lexical_error = None
    try:
        lexical_results = search_chunks(query, k=max(k * 2, k), document_ids=document_ids)
    except Exception as exc:
        lexical_error = str(exc)
        logger.exception("rag_lexical_retrieval_failed", extra={"reason": lexical_error})

    merged: list[tuple[str, dict]] = []
    seen: set[tuple[str, str]] = set()
    for doc, _score in semantic_results:
        metadata = doc.metadata or {}
        key = (doc.page_content, str(metadata.get("document_id", "")))
        if key not in seen:
            merged.append((doc.page_content, metadata))
            seen.add(key)
    for row in lexical_results:
        metadata = {key: row.get(key) for key in ("source", "filename", "document_id", "page", "document_type", "url")}
        key = (row["content"], str(row.get("document_id", "")))
        if key not in seen:
            merged.append((row["content"], metadata))
            seen.add(key)
        if len(merged) >= k:
            break

    context_parts = [content for content, _ in merged[:k]]
    sources = list(dict.fromkeys(_citation(metadata) for _, metadata in merged[:k]))
    mode = "hybrid" if semantic_results and lexical_results else "semantic" if semantic_results else "keyword" if lexical_results else "unavailable"
    result = {
        "context": "\n\n---\n\n".join(context_parts),
        "sources": sources,
        "passages": [{"content": content, "source": _citation(metadata)} for content, metadata in merged[:k]],
        "retrieval_mode": mode,
        "degraded": mode == "keyword",
    }
    if not merged and semantic_error and lexical_error:
        result["error"] = "Document search is unavailable: both semantic and keyword retrieval failed."
    return result
