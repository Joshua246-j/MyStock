"""Persistent SQLite full-text index used when semantic embeddings are unavailable."""
import re
from typing import Any

from sqlalchemy import text

from app.db.database import engine

_TOKEN = re.compile(r"[\w.-]+", re.UNICODE)


def ensure_lexical_index() -> None:
    """Create the FTS5 index lazily so existing installations migrate safely."""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks USING fts5(
                content, source UNINDEXED, filename UNINDEXED,
                document_id UNINDEXED, page UNINDEXED,
                document_type UNINDEXED, url UNINDEXED,
                tokenize='unicode61'
            )"""
        )


def index_chunks(chunks: list[str], metadata: dict[str, Any]) -> int:
    if not chunks:
        return 0
    ensure_lexical_index()
    records = []
    for chunk in chunks:
        records.append({
            "content": chunk,
            "source": str(metadata.get("source") or metadata.get("filename") or "Unknown"),
            "filename": str(metadata.get("filename") or ""),
            "document_id": str(metadata.get("document_id", "0")),
            "page": str(metadata.get("page", "")),
            "document_type": str(metadata.get("document_type") or "document"),
            "url": str(metadata.get("url") or ""),
        })
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO rag_chunks
            (content, source, filename, document_id, page, document_type, url)
            VALUES (:content, :source, :filename, :document_id, :page,
                    :document_type, :url)"""), records)
    return len(records)

def index_chunks_batch(chunks: list[str], metadatas: list[dict[str, Any]]) -> int:
    if not chunks:
        return 0
    ensure_lexical_index()
    records = []
    for chunk, metadata in zip(chunks, metadatas):
        records.append({
            "content": chunk,
            "source": str(metadata.get("source") or metadata.get("filename") or "Unknown"),
            "filename": str(metadata.get("filename") or ""),
            "document_id": str(metadata.get("document_id", "0")),
            "page": str(metadata.get("page", "")),
            "document_type": str(metadata.get("document_type") or "document"),
            "url": str(metadata.get("url") or ""),
        })
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO rag_chunks
            (content, source, filename, document_id, page, document_type, url)
            VALUES (:content, :source, :filename, :document_id, :page,
                    :document_type, :url)"""), records)
    return len(records)


def search_chunks(query: str, k: int = 5, document_ids: list[int] | None = None) -> list[dict[str, Any]]:
    terms = list(dict.fromkeys(token for token in _TOKEN.findall(query.casefold()) if len(token) > 1))
    if not terms or k < 1:
        return []
    ensure_lexical_index()
    # Quote each term to prevent user input from injecting FTS operators.
    match_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms[:24])
    sql = "SELECT content, source, filename, document_id, page, document_type, url, bm25(rag_chunks) AS rank FROM rag_chunks WHERE rag_chunks MATCH :query"
    params: dict[str, Any] = {"query": match_query, "limit": int(k)}
    if document_ids:
        placeholders = []
        for index, document_id in enumerate(document_ids):
            key = f"document_id_{index}"
            placeholders.append(f":{key}")
            params[key] = str(document_id)
        sql += f" AND document_id IN ({', '.join(placeholders)})"
    sql += " ORDER BY rank ASC LIMIT :limit"
    with engine.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def delete_document_chunks(document_id: int) -> int:
    ensure_lexical_index()
    with engine.begin() as connection:
        result = connection.execute(
            text("DELETE FROM rag_chunks WHERE document_id = :document_id"),
            {"document_id": str(document_id)},
        )
        return result.rowcount or 0


def lexical_index_available() -> bool:
    try:
        ensure_lexical_index()
        with engine.connect() as connection:
            connection.execute(text("SELECT count(*) FROM rag_chunks")).scalar_one()
        return True
    except Exception:
        return False
