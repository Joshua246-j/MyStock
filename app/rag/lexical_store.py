"""Persistent SQLite full-text index used when semantic embeddings are unavailable."""
import re
import json
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
        connection.exec_driver_sql(
            """CREATE TABLE IF NOT EXISTS rag_chunk_metadata (
                chunk_rowid INTEGER PRIMARY KEY,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )"""
        )
        connection.exec_driver_sql("""CREATE TABLE IF NOT EXISTS rag_vector_map (
            faiss_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_rowid INTEGER NOT NULL UNIQUE
        )""")
        # Preserve compatibility with FTS rows created by older releases.
        legacy = connection.execute(text("""SELECT f.rowid, f.source, f.filename,
            f.document_id, f.page, f.document_type, f.url
            FROM rag_chunks f LEFT JOIN rag_chunk_metadata m ON m.chunk_rowid=f.rowid
            WHERE m.chunk_rowid IS NULL""")).mappings().all()
        for row in legacy:
            metadata = {key: row[key] for key in ("source", "filename", "document_id", "page", "document_type", "url")}
            metadata["source_type"] = "web" if row["document_type"] == "web" else "user_upload"
            metadata["title"] = row["source"] or row["filename"]
            connection.execute(text("INSERT OR IGNORE INTO rag_chunk_metadata(chunk_rowid, metadata_json) VALUES (:rowid, :metadata)"),
                               {"rowid": row["rowid"], "metadata": json.dumps(metadata)})


def _insert_records(chunks: list[str], metadatas: list[dict[str, Any]]) -> list[int]:
    if not chunks:
        return []
    if len(chunks) != len(metadatas):
        raise ValueError("Every indexed chunk must have exactly one metadata record.")
    ensure_lexical_index()
    with engine.begin() as connection:
        rowids = []
        for chunk, metadata in zip(chunks, metadatas):
            row = {
                "content": chunk,
                "source": str(metadata.get("source") or metadata.get("title") or metadata.get("filename") or "Unknown"),
                "filename": str(metadata.get("filename") or ""),
                "document_id": str(metadata.get("document_id", "0")),
                "page": str(metadata.get("page", "")),
                "document_type": str(metadata.get("document_type") or "document"),
                "url": str(metadata.get("url") or metadata.get("source_url") or ""),
            }
            result = connection.execute(text("""INSERT INTO rag_chunks
                (content, source, filename, document_id, page, document_type, url)
                VALUES (:content, :source, :filename, :document_id, :page, :document_type, :url)"""), row)
            chunk_rowid = result.lastrowid
            rowids.append(int(chunk_rowid))
            connection.execute(text("""INSERT INTO rag_chunk_metadata(chunk_rowid, metadata_json)
                VALUES (:rowid, :metadata)"""), {
                    "rowid": chunk_rowid,
                    "metadata": json.dumps(metadata, ensure_ascii=False, default=str),
                })
    return rowids


def _index_records(chunks: list[str], metadatas: list[dict[str, Any]]) -> int:
    return len(_insert_records(chunks, metadatas))


def index_chunks(chunks: list[str], metadata: dict[str, Any]) -> int:
    return _index_records(chunks, [metadata for _ in chunks])

def index_chunks_batch(chunks: list[str], metadatas: list[dict[str, Any]]) -> int:
    return _index_records(chunks, metadatas)


def index_chunks_batch_with_ids(chunks: list[str], metadatas: list[dict[str, Any]]) -> list[int]:
    return _insert_records(chunks, metadatas)


def search_chunks(query: str, k: int = 5, document_ids: list[int] | None = None, metadata_filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    terms = list(dict.fromkeys(token for token in _TOKEN.findall(query.casefold()) if len(token) > 1))
    if not terms or k < 1:
        return []
    ensure_lexical_index()
    # Quote each term to prevent user input from injecting FTS operators.
    match_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms[:24])
    sql = "SELECT f.rowid AS chunk_rowid, f.content, f.source, f.filename, f.document_id, f.page, f.document_type, f.url, m.metadata_json, bm25(rag_chunks) AS rank FROM rag_chunks f LEFT JOIN rag_chunk_metadata m ON m.chunk_rowid=f.rowid WHERE rag_chunks MATCH :query"
    params: dict[str, Any] = {"query": match_query, "limit": int(k)}
    if document_ids:
        placeholders = []
        for index, document_id in enumerate(document_ids):
            key = f"document_id_{index}"
            placeholders.append(f":{key}")
            params[key] = str(document_id)
        sql += f" AND f.document_id IN ({', '.join(placeholders)})"
    fields = {"company", "ticker", "exchange", "country", "sector", "industry", "source_type", "document_type", "source_url", "title", "published_at", "filing_date", "period_start", "period_end"}
    for field, expected in (metadata_filter or {}).items():
        if field not in fields or expected is None:
            continue
        values = expected.get("$in") if isinstance(expected, dict) else None
        if values is None:
            values = [expected.get("$eq")] if isinstance(expected, dict) else expected if isinstance(expected, (list, tuple, set)) else [expected]
        values = [str(value) for value in values if value is not None]
        if not values:
            return []
        path = f"$.{field}"
        if len(values) == 1:
            key = f"filter_{field}"
            params[key] = values[0]
            sql += f" AND json_extract(m.metadata_json, '{path}') COLLATE NOCASE = :{key}"
        else:
            placeholders = []
            for index, value in enumerate(values):
                key = f"filter_{field}_{index}"
                params[key] = value
                placeholders.append(f":{key}")
            sql += f" AND json_extract(m.metadata_json, '{path}') COLLATE NOCASE IN ({', '.join(placeholders)})"
    sql += " ORDER BY rank ASC LIMIT :limit"
    with engine.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        metadata = json.loads(item.pop("metadata_json") or "{}")
        item.update(metadata)
        result.append(item)
    return result


def delete_document_chunks(document_id: int) -> int:
    ensure_lexical_index()
    with engine.begin() as connection:
        connection.execute(text("""DELETE FROM rag_vector_map WHERE chunk_rowid IN
            (SELECT rowid FROM rag_chunks WHERE document_id = :document_id)"""),
            {"document_id": str(document_id)})
        connection.execute(text("""DELETE FROM rag_chunk_metadata WHERE chunk_rowid IN
            (SELECT rowid FROM rag_chunks WHERE document_id = :document_id)"""),
            {"document_id": str(document_id)})
        result = connection.execute(
            text("DELETE FROM rag_chunks WHERE document_id = :document_id"),
            {"document_id": str(document_id)},
        )
        removed = result.rowcount or 0
    if removed:
        from app.rag.vector_store import invalidate_vector_index
        invalidate_vector_index()
    return removed


def lexical_index_available() -> bool:
    try:
        ensure_lexical_index()
        with engine.connect() as connection:
            connection.execute(text("SELECT count(*) FROM rag_chunks")).scalar_one()
        return True
    except Exception:
        return False


def clean_orphaned_chunks() -> int:
    """Reconcile the rag_chunks FTS5 table with the main db and FAISS vector map."""
    from app.db.database import SessionLocal
    from app.db.models import DocumentMetadata

    with SessionLocal() as db:
        valid_docs = {str(row.id) for row in db.query(DocumentMetadata.id).all()}

    ensure_lexical_index()
    deleted_count = 0
    with engine.begin() as conn:
        all_docs = conn.execute(text("SELECT DISTINCT document_id FROM rag_chunks")).fetchall()
        for (doc_id,) in all_docs:
            if str(doc_id) not in valid_docs and str(doc_id) != "0":
                conn.execute(text("DELETE FROM rag_vector_map WHERE chunk_rowid IN (SELECT rowid FROM rag_chunks WHERE document_id = :doc)"), {"doc": doc_id})
                conn.execute(text("DELETE FROM rag_chunk_metadata WHERE chunk_rowid IN (SELECT rowid FROM rag_chunks WHERE document_id = :doc)"), {"doc": doc_id})
                res = conn.execute(text("DELETE FROM rag_chunks WHERE document_id = :doc"), {"doc": doc_id})
                deleted_count += (res.rowcount or 0)

        res_map = conn.execute(text("DELETE FROM rag_vector_map WHERE chunk_rowid NOT IN (SELECT rowid FROM rag_chunks)"))
        res_meta = conn.execute(text("DELETE FROM rag_chunk_metadata WHERE chunk_rowid NOT IN (SELECT rowid FROM rag_chunks)"))
        deleted_count += (res_map.rowcount or 0) + (res_meta.rowcount or 0)

    if deleted_count > 0:
        from app.rag.vector_store import invalidate_vector_index, get_vector_store
        invalidate_vector_index()
        get_vector_store()

    return deleted_count

