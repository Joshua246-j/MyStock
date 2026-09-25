import uuid
import re
from pathlib import Path
import asyncio
from sqlalchemy.orm import Session
from app.db.models import ChatSession, ChatMessage, UserSettings, DocumentMetadata
from app.config import UPLOAD_DIR, OLLAMA_MODEL
from app.analysis.orchestrator import orchestrate_chat
from app.ollama_client import OllamaError
import logging
from typing import Literal

logger = logging.getLogger("stockrag.chat_service")

class ChatService:
    def __init__(self, db: Session):
        self.db = db

    def _get_settings(self) -> dict:
        record = self.db.query(UserSettings).first()
        return record.settings if record else {}

    def get_session(self, session_id: str):
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if not session:
            return None
        messages = self.db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at, ChatMessage.id).all()
        return {"session_id": session_id, "messages": [{"role": row.role, "content": row.content, "created_at": row.created_at.isoformat()} for row in messages]}

    def chat(self, message: str, dataset_id: int | None, dataset_path: str | None, symbol: str | None, session_id: str | None, mode: Literal["auto", "market", "documents", "general"] | None, document_ids: list[int] | None):
        settings = self._get_settings()
        ai_model = settings.get("ai_model", OLLAMA_MODEL)
        
        selected_document_ids = []
        if document_ids:
            records = self.db.query(DocumentMetadata).filter(DocumentMetadata.id.in_(document_ids), DocumentMetadata.document_type == "pdf", DocumentMetadata.status == "completed").all()
            selected_document_ids = [record.id for record in records]
            if len(selected_document_ids) != len(set(document_ids)):
                raise ValueError("One or more selected documents are unavailable for retrieval")
                
        resolved_dataset_path = None
        if dataset_id is not None:
            dataset_record = self.db.query(DocumentMetadata).filter(DocumentMetadata.id == dataset_id, DocumentMetadata.document_type == "dataset", DocumentMetadata.status == "completed").first()
            if not dataset_record or not dataset_record.storage_path:
                raise ValueError("Selected dataset is unavailable")
            resolved_dataset_path = Path(dataset_record.storage_path).resolve()
            uploads_root = Path(UPLOAD_DIR).resolve()
            if uploads_root not in resolved_dataset_path.parents or resolved_dataset_path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
                raise ValueError("Dataset path is outside the upload directory")
            if not resolved_dataset_path.is_file():
                raise ValueError("Selected dataset file is missing")
            resolved_dataset_path = str(resolved_dataset_path)
        elif dataset_path:
            raise ValueError("Use a stored dataset ID instead of a filesystem path")

        if not session_id:
            session_id = str(uuid.uuid4())
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        created_session = session is None
        if not session:
            session = ChatSession(session_id=session_id)
            self.db.add(session)
            self.db.commit()

        history_records = self.db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(15).all()
        history = list(reversed(history_records))
        formatted_history = [
            {"role": msg.role, "content": msg.content}
            for msg in history
            if msg.role in {"user", "assistant"}
            and not (msg.role == "assistant" and re.match(r"^(?:Error:\s*Could not connect to Ollama|AI response unavailable:|Analysis failed before a response could be generated\.)", msg.content, re.IGNORECASE))
        ]

        user_msg = ChatMessage(session_id=session_id, role="user", content=message)
        self.db.add(user_msg)
        self.db.commit()

        try:
            result = asyncio.run(orchestrate_chat(
                message=message,
                symbol=symbol,
                dataset_path=resolved_dataset_path,
                history=formatted_history,
                model=ai_model,
                settings=settings,
                mode=mode,
                document_ids=selected_document_ids or None,
            ))
        except OllamaError as exc:
            logger.warning("chat_generation_unavailable", extra={"session_id": session_id, "error_code": exc.code, "reason": str(exc)})
            self.db.delete(user_msg)
            if created_session and not formatted_history:
                self.db.delete(session)
            self.db.commit()
            raise exc
        except Exception as exc:
            logger.exception("chat_orchestration_failed", extra={"session_id": session_id})
            self.db.delete(user_msg)
            if created_session and not formatted_history:
                self.db.delete(session)
            self.db.commit()
            raise exc
            
        asst_msg = ChatMessage(session_id=session_id, role="assistant", content=result["answer"], sources=result["citations"])
        self.db.add(asst_msg)
        self.db.commit()
        result["session_id"] = session_id
        return result
