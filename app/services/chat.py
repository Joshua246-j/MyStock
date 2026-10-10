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
from sqlalchemy import func

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
        return {
            "session_id": session_id,
            "parent_session_id": session.parent_session_id,
            "branch_from_message_id": session.branch_from_message_id,
            "document_ids": session.document_ids or [],
            "dataset_id": session.dataset_id,
            "messages": [{"id": row.id, "role": row.role, "content": row.content, "created_at": row.created_at.isoformat(), "sources": row.sources or [], "metadata": row.metadata_json or {}} for row in messages],
        }

    def list_sessions(self, limit: int = 50):
        """Return recent saved conversations with a title and a short preview."""
        rows = (
            self.db.query(ChatSession.session_id, ChatSession.created_at, ChatSession.parent_session_id, func.max(ChatMessage.created_at).label("updated_at"), func.count(ChatMessage.id).label("message_count"))
            .join(ChatMessage, ChatMessage.session_id == ChatSession.session_id)
            .group_by(ChatSession.id, ChatSession.session_id, ChatSession.created_at, ChatSession.parent_session_id)
            .order_by(func.max(ChatMessage.created_at).desc(), ChatSession.id.desc())
            .limit(max(1, min(int(limit), 100)))
            .all()
        )
        ids = [row.session_id for row in rows]
        first_user = {}
        if ids:
            messages = self.db.query(ChatMessage).filter(ChatMessage.session_id.in_(ids), ChatMessage.role == "user").order_by(ChatMessage.created_at, ChatMessage.id).all()
            for message in messages:
                first_user.setdefault(message.session_id, message.content)
        return [{
            "session_id": row.session_id,
            "parent_session_id": row.parent_session_id,
            "is_branch": bool(row.parent_session_id),
            "title": (first_user.get(row.session_id) or "New conversation").strip()[:80],
            "preview": (first_user.get(row.session_id) or "No user message").strip()[:120],
            "message_count": int(row.message_count),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        } for row in rows]

    def branch_session(self, session_id: str, message_id: int) -> dict:
        source_session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if not source_session:
            raise LookupError("Chat session not found")
        anchor = self.db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.session_id == session_id,
            ChatMessage.role.in_(("user", "assistant")),
        ).first()
        if not anchor:
            raise ValueError("Choose a message in this conversation to branch from")
        if anchor.role == "assistant" and re.match(r"^(?:Error:\s*Could not connect to Ollama|AI response unavailable:|Analysis failed before a response could be generated\.)", anchor.content or "", re.IGNORECASE):
            raise ValueError("A failed response cannot be used as a branch point")

        branch_id = str(uuid.uuid4())
        branch = ChatSession(
            session_id=branch_id,
            parent_session_id=session_id,
            branch_from_message_id=anchor.id,
            document_ids=source_session.document_ids or [],
            dataset_id=source_session.dataset_id,
        )
        self.db.add(branch)
        self.db.flush()
        messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id,
            ChatMessage.id <= anchor.id,
        ).order_by(ChatMessage.id).all()
        for message in messages:
            self.db.add(ChatMessage(
                session_id=branch_id,
                role=message.role,
                content=message.content,
                sources=message.sources,
                metadata_json=message.metadata_json or {},
            ))
        self.db.commit()
        return {"session_id": branch_id, "parent_session_id": session_id, "branch_from_message_id": anchor.id}

    def delete_session(self, session_id: str) -> bool:
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if not session:
            return False
        # Branches contain a full copy of their conversation prefix. If their
        # source is removed, keep those copies usable and mark them as roots.
        self.db.query(ChatSession).filter(ChatSession.parent_session_id == session_id).update(
            {ChatSession.parent_session_id: None, ChatSession.branch_from_message_id: None},
            synchronize_session=False,
        )
        self.db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete(synchronize_session=False)
        self.db.delete(session)
        self.db.commit()
        return True

    def chat(self, message: str, dataset_id: int | None, dataset_path: str | None, symbol: str | None, session_id: str | None, mode: Literal["auto", "market", "documents", "general"] | None, document_ids: list[int] | None, chart_period: str | None = None, chart_interval: str | None = None, chart_mode: str | None = None, chart_view: str | None = None, token_callback=None):
        settings = self._get_settings()
        ai_model = settings.get("ai_model", OLLAMA_MODEL)
        
        selected_document_ids = []
        if document_ids:
            research_formats = {"pdf", "docx", "txt", "html", "web"}
            records = self.db.query(DocumentMetadata).filter(DocumentMetadata.id.in_(document_ids), DocumentMetadata.document_type.in_(research_formats), DocumentMetadata.status == "completed").all()
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
        session.document_ids = selected_document_ids
        session.dataset_id = dataset_id
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
        user_message_id = user_msg.id

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
                chart_period=chart_period,
                chart_interval=chart_interval,
                chart_mode=chart_mode,
                chart_view=chart_view,
                on_token=token_callback,
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
            
        reply_metadata = {
            key: result.get(key) for key in (
                "model", "data_timestamp", "retrieval", "sources_unverified", "format_unverified",
                "numeric_validation", "answer_method", "data_status", "structured_analysis",
            )
        }
        asst_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=result["answer"],
            sources=result["citations"],
            metadata_json=reply_metadata,
        )
        self.db.add(asst_msg)
        self.db.commit()
        result["session_id"] = session_id
        result["user_message_id"] = user_message_id
        result["assistant_message_id"] = asst_msg.id
        return result
