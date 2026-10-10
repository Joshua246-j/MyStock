import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import DocumentMetadata
from app.services.chat import ChatService


def test_chat_accepts_selected_pdf_docx_txt_html_and_crawled_web_documents(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    captured = {}

    async def fake_orchestrate_chat(**kwargs):
        captured.update(kwargs)
        return {"answer": "Evidence answer", "citations": [], "retrieval": {}, "model": "fixture"}

    monkeypatch.setattr("app.services.chat.orchestrate_chat", fake_orchestrate_chat)
    with session_factory() as db:
        for file_type in ("pdf", "docx", "txt", "html", "web"):
            db.add(DocumentMetadata(filename=f"research.{file_type}", document_type=file_type, status="completed"))
        db.commit()
        ids = [row.id for row in db.query(DocumentMetadata).order_by(DocumentMetadata.id).all()]

        result = ChatService(db).chat("Summarize selected research", None, None, None, None, "documents", ids)

        assert result["answer"] == "Evidence answer"
        assert captured["document_ids"] == ids
