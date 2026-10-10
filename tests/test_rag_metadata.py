from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.rag import lexical_store


def test_fts_metadata_filter_preserves_document_fields_and_delete_cleans_index(monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(lexical_store, "engine", test_engine)

    chunks = [
        "Risk factors include foreign exchange and supply disruptions.",
        "Risk factors include cloud competition and data privacy.",
    ]
    metadata = [
        {"document_id": 101, "filename": "apple-10k.pdf", "title": "Apple 2025 10-K", "ticker": "AAPL", "company": "Apple Inc.", "document_type": "10-K", "source_type": "sec_filing", "filing_date": "2025-11-01", "page": 8, "chunk_index": 0, "content_hash": "hash-a"},
        {"document_id": 202, "filename": "msft-10k.pdf", "title": "Microsoft 2025 10-K", "ticker": "MSFT", "company": "Microsoft", "document_type": "10-K", "source_type": "sec_filing", "filing_date": "2025-10-25", "page": 12, "chunk_index": 0, "content_hash": "hash-b"},
    ]
    assert lexical_store.index_chunks_batch(chunks, metadata) == 2

    result = lexical_store.search_chunks(
        "risk factors",
        k=5,
        metadata_filter={"ticker": "AAPL", "document_type": "10-K"},
    )

    assert len(result) == 1
    assert result[0]["ticker"] == "AAPL"
    assert result[0]["company"] == "Apple Inc."
    assert result[0]["filing_date"] == "2025-11-01"
    assert result[0]["chunk_index"] == 0

    assert lexical_store.delete_document_chunks(101) == 1
    with test_engine.connect() as connection:
        remaining_metadata = connection.execute(text("SELECT COUNT(*) FROM rag_chunk_metadata")).scalar_one()
    assert remaining_metadata == 1
    test_engine.dispose()
