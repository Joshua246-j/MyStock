import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import chat as chat_routes
from app.api.routes.chat import ChatRequest, stream_chat
from app.db.database import Base
from app.db.models import ChatMessage
from app.services.chat import ChatService


def test_streaming_chat_emits_tokens_then_persists_final_reply(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(chat_routes, "SessionLocal", factory)

    async def fake_orchestrate_chat(**kwargs):
        kwargs["on_token"]("Hello")
        kwargs["on_token"](" from Ollama")
        return {
            "answer":"Hello from Ollama", "citations":[], "retrieval":{}, "model":"fixture",
            "data_status":"NOT_REQUESTED", "data_timestamp":"2026-10-09T00:00:00+00:00",
            "answer_method":"model_generated",
        }

    monkeypatch.setattr("app.services.chat.orchestrate_chat", fake_orchestrate_chat)

    async def consume():
        response = await stream_chat(ChatRequest(message="Say hello"))
        return "".join([chunk async for chunk in response.body_iterator])

    payload = asyncio.run(consume())
    assert 'event: token\ndata: {"text":"Hello"}' in payload
    assert 'event: token\ndata: {"text":" from Ollama"}' in payload
    assert 'event: done\ndata: ' in payload
    assert '"answer":"Hello from Ollama"' in payload
    with factory() as db:
        rows = db.query(ChatMessage).order_by(ChatMessage.id).all()
        assert [(row.role, row.content) for row in rows] == [
            ("user", "Say hello"), ("assistant", "Hello from Ollama"),
        ]
        assert rows[1].metadata_json["model"] == "fixture"
        assert rows[1].metadata_json["answer_method"] == "model_generated"
        restored = ChatService(db).get_session(rows[1].session_id)
        assert restored["messages"][1]["metadata"]["model"] == "fixture"
    engine.dispose()
