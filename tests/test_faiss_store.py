import json

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.rag import lexical_store, vector_store


class FixtureEmbeddings:
    def __init__(self):
        self.document_batch_sizes = []

    @staticmethod
    def _vector(text):
        value = str(text).casefold()
        return [1.0, 0.0] if "apple" in value or "aapl" in value else [0.0, 1.0]

    def embed_documents(self, texts):
        self.document_batch_sizes.append(len(texts))
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


def test_faiss_persistence_and_metadata_filtering(tmp_path, monkeypatch, request):
    request.addfinalizer(lambda: (setattr(vector_store, "_INDEX", None), setattr(vector_store, "_INDEX_MODEL", None)))
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(lexical_store, "engine", test_engine)
    monkeypatch.setattr(vector_store, "engine", test_engine)
    monkeypatch.setattr(vector_store, "_INDEX_FILE", tmp_path / "chunks.faiss")
    monkeypatch.setattr(vector_store, "_INFO_FILE", tmp_path / "index.json")
    embeddings = FixtureEmbeddings()
    monkeypatch.setattr(vector_store, "get_embeddings", lambda: embeddings)
    monkeypatch.setattr(vector_store, "_INDEX", None)
    monkeypatch.setattr(vector_store, "_INDEX_MODEL", None)

    texts = ["Apple AAPL revenue increased to 735 million."]
    metadatas = [{"document_id": 10, "filename": "apple.txt", "ticker": "AAPL", "source_type": "user_upload"}]
    row_ids = lexical_store.index_chunks_batch_with_ids(texts, metadatas)
    store = vector_store.get_vector_store()
    store.add_texts(texts, metadatas, row_ids)
    new_texts = ["Acme industrial sales increased to 41 million."]
    new_metadata = [{"document_id": 20, "filename": "acme.txt", "ticker": "ACME", "source_type": "user_upload"}]
    new_row_ids = lexical_store.index_chunks_batch_with_ids(new_texts, new_metadata)
    store.add_texts(new_texts, new_metadata, new_row_ids)
    assert embeddings.document_batch_sizes == [1, 1]

    hits = store.similarity_search_with_score("Apple AAPL", k=2, filter={"ticker": "AAPL"})
    assert len(hits) == 1
    assert hits[0][0].metadata["ticker"] == "AAPL"
    assert "735 million" in hits[0][0].page_content

    monkeypatch.setattr(vector_store, "_INDEX", None)
    monkeypatch.setattr(vector_store, "_INDEX_MODEL", None)
    persisted = store.similarity_search_with_score("Apple AAPL", k=2)
    assert persisted
    assert json.loads((tmp_path / "index.json").read_text())["embedding_model"] == vector_store.EMBEDDING_MODEL
