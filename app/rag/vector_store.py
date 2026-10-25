"""Persistent FAISS CPU index with SQLite as the authoritative chunk/metadata store."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import RLock
from typing import Any

try:
    import faiss
    from langchain_core.documents import Document
except ImportError:
    faiss = None
    Document = None

import numpy as np
from sqlalchemy import text

from app.config import EMBEDDING_MODEL, FAISS_PATH
from app.db.database import engine
from app.rag.lexical_store import ensure_lexical_index
from app.rag.vector_embeddings import get_embeddings

logger = logging.getLogger("stockrag.rag.faiss")
_INDEX_FILE = Path(FAISS_PATH) / "chunks.faiss"
_INFO_FILE = Path(FAISS_PATH) / "index.json"
_LOCK = RLock()
_INDEX = None
_INDEX_MODEL: str | None = None


def _ensure_mapping_table() -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE IF NOT EXISTS rag_vector_map (
            faiss_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_rowid INTEGER NOT NULL UNIQUE
        )""")
        # FTS5 is the migration source of truth for chunks indexed before FAISS was enabled.
        connection.exec_driver_sql("""INSERT OR IGNORE INTO rag_vector_map(chunk_rowid)
            SELECT rowid FROM rag_chunks""")


def _load_index_locked() -> None:
    global _INDEX, _INDEX_MODEL
    if _INDEX is not None:
        return
    _INDEX_MODEL = None
    if _INDEX_FILE.is_file() and _INFO_FILE.is_file():
        try:
            info = json.loads(_INFO_FILE.read_text(encoding="utf-8"))
            _INDEX = faiss.read_index(str(_INDEX_FILE))
            _INDEX_MODEL = info.get("embedding_model")
        except Exception:
            logger.exception("faiss_index_load_failed")
            _INDEX = None
            _INDEX_MODEL = None


def _mapping_rows() -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""SELECT v.faiss_id, f.content, m.metadata_json
            FROM rag_vector_map v
            JOIN rag_chunks f ON f.rowid=v.chunk_rowid
            LEFT JOIN rag_chunk_metadata m ON m.chunk_rowid=f.rowid
            ORDER BY v.faiss_id""")).mappings().all()
    return [dict(row) for row in rows]


def _persist_locked(index, model: str) -> None:
    _INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_index = _INDEX_FILE.with_suffix(".faiss.next")
    temp_info = _INFO_FILE.with_suffix(".json.next")
    faiss.write_index(index, str(temp_index))
    temp_info.write_text(json.dumps({"embedding_model": model, "dimension": index.d}), encoding="utf-8")
    os.replace(temp_index, _INDEX_FILE)
    os.replace(temp_info, _INFO_FILE)


def _embed_texts(texts: list[str]) -> np.ndarray:
    embeddings = get_embeddings().embed_documents(texts)
    vectors = np.asarray(embeddings, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(texts) or vectors.shape[1] == 0:
        raise RuntimeError("The embedding service returned an invalid vector matrix.")
    if not np.isfinite(vectors).all():
        raise RuntimeError("The embedding service returned non-finite values.")
    faiss.normalize_L2(vectors)
    return vectors


def _rebuild_locked(rows: list[dict[str, Any]]):
    global _INDEX, _INDEX_MODEL
    if not rows:
        _INDEX = None
        _INDEX_MODEL = EMBEDDING_MODEL
        _INDEX_FILE.unlink(missing_ok=True)
        _INFO_FILE.unlink(missing_ok=True)
        return None
    rebuilt = None
    for start in range(0, len(rows), 64):
        batch = rows[start:start + 64]
        vectors = _embed_texts([row["content"] for row in batch])
        if rebuilt is None:
            rebuilt = faiss.IndexIDMap2(faiss.IndexFlatIP(int(vectors.shape[1])))
        if rebuilt.d != vectors.shape[1]:
            raise RuntimeError("Embedding dimensions changed while rebuilding the FAISS index.")
        ids = np.asarray([row["faiss_id"] for row in batch], dtype=np.int64)
        rebuilt.add_with_ids(vectors, ids)
    _persist_locked(rebuilt, EMBEDDING_MODEL)
    _INDEX = rebuilt
    _INDEX_MODEL = EMBEDDING_MODEL
    logger.info("faiss_index_rebuilt", extra={"vectors": rebuilt.ntotal, "embedding_model": EMBEDDING_MODEL})
    return _INDEX


def _append_rows_locked(rows: list[dict[str, Any]]):
    global _INDEX, _INDEX_MODEL
    for start in range(0, len(rows), 64):
        batch = rows[start:start + 64]
        vectors = _embed_texts([row["content"] for row in batch])
        if _INDEX is None:
            _INDEX = faiss.IndexIDMap2(faiss.IndexFlatIP(int(vectors.shape[1])))
        if _INDEX.d != vectors.shape[1]:
            return _rebuild_locked(_mapping_rows())
        ids = np.asarray([row["faiss_id"] for row in batch], dtype=np.int64)
        _INDEX.add_with_ids(vectors, ids)
    if _INDEX is not None:
        _persist_locked(_INDEX, EMBEDDING_MODEL)
        _INDEX_MODEL = EMBEDDING_MODEL
        logger.info("faiss_index_updated", extra={"added_vectors": len(rows), "total_vectors": _INDEX.ntotal})
    return _INDEX


def _ensure_current_locked():
    global _INDEX, _INDEX_MODEL
    ensure_lexical_index()
    _ensure_mapping_table()
    _load_index_locked()
    rows = _mapping_rows()
    active_ids = {int(row["faiss_id"]) for row in rows}
    indexed_ids = set()
    if _INDEX is not None:
        indexed_ids = set(int(value) for value in faiss.vector_to_array(_INDEX.id_map).tolist())
    if _INDEX_MODEL != EMBEDDING_MODEL:
        return _rebuild_locked(rows)
    if indexed_ids - active_ids:
        return _rebuild_locked(rows)
    if active_ids - indexed_ids:
        missing_ids = active_ids - indexed_ids
        return _append_rows_locked([row for row in rows if int(row["faiss_id"]) in missing_ids])
    if rows and _INDEX is None:
        return _rebuild_locked(rows)
    return _INDEX


def _where_clauses(where: dict | None) -> list[tuple[str, Any]]:
    if not where:
        return []
    clauses = []
    for field, value in where.items():
        if field == "$and" and isinstance(value, list):
            for nested in value:
                clauses.extend(_where_clauses(nested))
        elif not field.startswith("$"):
            clauses.append((field, value))
    return clauses


def _filtered_rows(where: dict) -> list[dict[str, Any]]:
    clauses = _where_clauses(where)
    allowed_metadata = {"company", "ticker", "exchange", "country", "sector", "industry", "source_type", "document_type", "source_url", "title", "published_at", "filing_date", "period_start", "period_end"}
    conditions = []
    params: dict[str, Any] = {}
    for number, (field, raw) in enumerate(clauses):
        values = raw.get("$in") if isinstance(raw, dict) else None
        if values is None:
            values = [raw.get("$eq")] if isinstance(raw, dict) else raw if isinstance(raw, (list, tuple, set)) else [raw]
        values = [value for value in values if value is not None]
        if not values:
            return []
        if field == "document_id":
            expression = "f.document_id"
            values = [str(value) for value in values]
        elif field in allowed_metadata:
            expression = f"json_extract(m.metadata_json, '$.{field}') COLLATE NOCASE"
            values = [str(value) for value in values]
        else:
            continue
        keys = []
        for index, value in enumerate(values):
            key = f"filter_{number}_{index}"
            params[key] = value
            keys.append(f":{key}")
        conditions.append(f"{expression} IN ({', '.join(keys)})")
    sql = """SELECT v.faiss_id, f.content, m.metadata_json FROM rag_vector_map v
        JOIN rag_chunks f ON f.rowid=v.chunk_rowid
        LEFT JOIN rag_chunk_metadata m ON m.chunk_rowid=f.rowid"""
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY v.faiss_id"
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql), params).mappings().all()]


def _to_document(row: dict[str, Any]) -> Document:
    metadata = json.loads(row.get("metadata_json") or "{}")
    metadata.setdefault("chunk_rowid", row.get("chunk_rowid"))
    return Document(page_content=row["content"], metadata=metadata)


class FaissVectorStore:
    """Small local vector adapter; SQLite metadata is filtered before vector scoring."""

    def add_texts(self, texts: list[str], metadatas: list[dict[str, Any]], chunk_ids: list[int] | None = None):
        if not texts:
            return []
        if not chunk_ids or len(texts) != len(metadatas) or len(texts) != len(chunk_ids):
            raise ValueError("FAISS indexing requires one SQLite FTS row ID per text and metadata record.")
        ensure_lexical_index()
        _ensure_mapping_table()
        with engine.begin() as connection:
            for chunk_id in chunk_ids:
                connection.execute(text("INSERT OR IGNORE INTO rag_vector_map(chunk_rowid) VALUES (:chunk_id)"), {"chunk_id": int(chunk_id)})
        with _LOCK:
            index = _ensure_current_locked()
            return list(range(len(texts))) if index is not None else []

    def similarity_search_with_score(self, query: str, k: int = 4, filter: dict | None = None):
        if k < 1:
            return []
        with _LOCK:
            index = _ensure_current_locked()
            if index is None or index.ntotal == 0:
                return []
            query_vector = np.asarray([get_embeddings().embed_query(query)], dtype=np.float32)
            if query_vector.shape[1] != index.d:
                raise RuntimeError("Query embedding dimensions do not match the saved FAISS index.")
            faiss.normalize_L2(query_vector)
            if filter:
                rows = _filtered_rows(filter)
                scored = []
                for offset in range(0, len(rows), 512):
                    batch = rows[offset:offset + 512]
                    if not batch:
                        continue
                    vectors = np.asarray([index.reconstruct(int(row["faiss_id"])) for row in batch], dtype=np.float32)
                    scores = vectors @ query_vector[0]
                    scored.extend((float(score), row) for score, row in zip(scores, batch))
                scored.sort(key=lambda pair: pair[0], reverse=True)
                return [(_to_document(row), float(1.0 - score)) for score, row in scored[:k]]
            scores, ids = index.search(query_vector, min(k, index.ntotal))
            wanted = [int(value) for value in ids[0] if int(value) >= 0]
            if not wanted:
                return []
            placeholders = ",".join(f":id_{i}" for i in range(len(wanted)))
            params = {f"id_{i}": value for i, value in enumerate(wanted)}
            with engine.connect() as connection:
                records = connection.execute(text(f"""SELECT v.faiss_id, f.content, f.rowid AS chunk_rowid, m.metadata_json
                    FROM rag_vector_map v JOIN rag_chunks f ON f.rowid=v.chunk_rowid
                    LEFT JOIN rag_chunk_metadata m ON m.chunk_rowid=f.rowid
                    WHERE v.faiss_id IN ({placeholders})"""), params).mappings().all()
            by_id = {int(row["faiss_id"]): dict(row) for row in records}
            results = []
            for vector_id, score in zip(ids[0], scores[0]):
                row = by_id.get(int(vector_id))
                if row:
                    results.append((_to_document(row), float(1.0 - score)))
            return results

    def health_check(self) -> bool:
        if faiss is None:
            return False
        try:
            with _LOCK:
                _ensure_current_locked()
            return True
        except Exception:
            logger.exception("faiss_health_check_failed")
            return False


_VECTOR_STORE = FaissVectorStore()


def get_vector_store() -> FaissVectorStore:
    return _VECTOR_STORE


def invalidate_vector_index() -> None:
    """Force the next retrieval to reconcile SQLite IDs and the persisted index."""
    global _INDEX
    with _LOCK:
        _INDEX = None
