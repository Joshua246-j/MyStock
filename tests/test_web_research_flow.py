import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis import orchestrator
from app.db.database import Base
from app.db.models import DocumentMetadata


def test_natural_language_web_research_indexes_and_retrieves_scoped_evidence(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.db.database.SessionLocal", factory)
    monkeypatch.setattr("app.rag.lexical_store.index_chunks_batch_with_ids", lambda _texts, _metadata: [1])

    source_url = "https://news.google.com/rss/articles/story-123"
    search_result = {
        "title": "Company reports quarterly outlook — Reuters",
        "url": source_url,
        "publisher": "Reuters",
        "publisher_url": "https://www.reuters.com/",
        "snippet": "The company announced a quarterly outlook.",
        "published_at": "Thu, 08 Oct 2026 10:00:00 GMT",
    }
    monkeypatch.setattr("app.web.crawler.search_web", lambda *_args, **_kwargs: [search_result])

    retrieved_scopes = []

    class Retriever:
        def retrieve_context(self, _query, k=5, document_ids=None, **_kwargs):
            retrieved_scopes.append(document_ids)
            return {
                "context": "Search result title: Company reports quarterly outlook — Reuters\nSearch result excerpt: The company announced a quarterly outlook.",
                "sources": [f"Company reports quarterly outlook — Reuters\n{source_url}"],
                "retrieval_mode": "keyword",
                "passages": [],
            }

    class Prompt:
        def build(self, message, history, context, detail, local_model=""):
            assert "Search result excerpt" in "\n".join(context)
            return orchestrator.PromptBuilder().build(message, history, context, detail, local_model=local_model)

    class Ollama:
        model = "qwen2.5:1.5b"
        async def check_health(self, _timeout): return True
        async def chat(self, messages, _model, **_kwargs):
            assert "untrusted_evidence_json" in messages[-1]["content"]
            assert "Search result excerpt" in messages[-1]["content"]
            return (
                "## Answer\nReuters reports a quarterly outlook.\n\n"
                "## Key Facts\n- The result is a search excerpt.\n\n"
                "## Analysis\nThe excerpt is limited evidence.\n\n"
                "## Limitations\nThis is not the full article.\n\n"
                f"## Sources\n{source_url}"
            )

    monkeypatch.setattr(orchestrator, "ollama_client", Ollama())

    result = asyncio.run(orchestrator.orchestrate_chat(
        "Search the web for recent company news from Reuters.",
        settings={"request_timeout": 5, "max_retrieved_documents": 5, "web_research_enabled": True},
        retriever=Retriever(),
        prompt_builder=Prompt(),
    ))

    assert result["structured_analysis"]["intents"] == ["web_research"]
    assert result["retrieval"]["web_sources"] == 1
    assert retrieved_scopes and len(retrieved_scopes[0]) == 1
    assert source_url in result["citations"][0]
    duplicate = asyncio.run(orchestrator.orchestrate_chat(
        "Search the web for recent company news from Reuters.",
        settings={"request_timeout": 5, "max_retrieved_documents": 5, "web_research_enabled": True},
        retriever=Retriever(),
        prompt_builder=Prompt(),
    ))
    assert duplicate["retrieval"]["web_sources"] == 1
    assert retrieved_scopes[0] == retrieved_scopes[1]
    with factory() as db:
        indexed_rows = db.query(DocumentMetadata).filter_by(document_type="web", status="completed").all()
        assert len(indexed_rows) == 1
        indexed = indexed_rows[0]
        assert indexed.metadata_json["excerpt_scope"] == "search_result_excerpt"
        assert indexed.metadata_json["source_url"] == source_url
    engine.dispose()
