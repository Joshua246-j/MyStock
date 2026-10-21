import uuid
import re
from pathlib import Path
import asyncio
from sqlalchemy.orm import Session
from app.db.models import ChatSession, ChatMessage, UserSettings, DocumentMetadata
from app.config import UPLOAD_DIR, OLLAMA_MODEL
from app.analysis.orchestrator import orchestrate_chat
from app.ollama_client import OllamaError
from app.services.memory import MemoryService, extract_memory_directive
import logging
from typing import Literal
from sqlalchemy import func

logger = logging.getLogger("stockrag.chat_service")


def generate_conversation_title(message: str, symbol: str | None = None) -> str:
    """Generate a clean, high-signal, logical conversation title based on context."""
    if not message or not message.strip():
        return f"{symbol} Analysis" if symbol else "New Conversation"
    raw = message.strip()
    clean = re.sub(r"[?!.,;:\'\"]+", " ", raw)
    clean = " ".join(clean.split())
    
    tickers = re.findall(r"\b[A-Z]{2,5}(?:\.NS)?\b", raw)
    if not tickers and symbol:
        tickers = [symbol]
    
    if len(tickers) >= 2:
        return f"{tickers[0]} vs {tickers[1]} Comparison"
    
    t = tickers[0] if tickers else symbol
    low = raw.lower()
    
    if "sharpe ratio" in low:
        return "Sharpe Ratio in Python" if "python" in low else "Sharpe Ratio Analysis"
    if "maximum drawdown" in low or "max drawdown" in low:
        return "Maximum Drawdown Calculation"
    if "dividend" in low:
        return f"{t} Dividend Analysis" if t else "Dividend Yield & Valuation"
    if "porter" in low and "force" in low:
        return "Porter's Five Forces"
    if "swot" in low:
        return f"{t} SWOT Analysis" if t else "SWOT Strategic Analysis"
    if "dcf" in low or "discounted cash flow" in low:
        return f"{t} DCF Valuation" if t else "DCF Valuation Model"
    
    if t:
        if any(w in low for w in ["news", "headline", "article"]):
            return f"{t} Market News"
        if any(w in low for w in ["technical", "rsi", "macd", "indicator", "moving average", "chart", "trend"]):
            return f"{t} Technical Analysis"
        if any(w in low for w in ["fundamental", "earnings", "revenue", "p/e", "pe ratio", "balance sheet", "financial"]):
            return f"{t} Fundamentals & Valuation"
        if any(w in low for w in ["analyze", "analysis", "overview", "outlook"]):
            return f"{t} Market Overview"
            
    subj = re.sub(
        r"^(?:can\s+you\s+|could\s+you\s+|please\s+|tell\s+me\s+about\s+|tell\s+me\s+|show\s+me\s+|explain\s+how\s+|explain\s+what\s+|explain\s+|give\s+me\s+|what\s+is\s+the\s+difference\s+between\s+|what\s+is\s+the\s+|what\s+are\s+the\s+|what\s+is\s+|what\s+are\s+|how\s+does\s+|how\s+do\s+|how\s+to\s+|write\s+a\s+|calculate\s+|find\s+)",
        "",
        clean,
        flags=re.IGNORECASE
    ).strip()
    words = [w for w in subj.split() if w.lower() not in {"a", "an", "the", "for", "to", "in", "of", "and", "with", "on", "all", "is", "are"}]
    if not words:
        words = clean.split()
    top_words = words[:4]
    
    formatted = []
    for w in top_words:
        if w.isupper() and len(w) <= 6:
            formatted.append(w)
        else:
            formatted.append(w.capitalize())
    title = " ".join(formatted).strip()
    return title[:42] or (f"{t} Research" if t else "Discussion")


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
            "is_pinned": bool(getattr(session, "is_pinned", 0)),
            "title": session.title,
            "messages": [{"id": row.id, "role": row.role, "content": row.content, "created_at": row.created_at.isoformat(), "sources": row.sources or [], "metadata": row.metadata_json or {}} for row in messages],
        }

    def list_sessions(self, limit: int = 50):
        """Return recent saved conversations with a title, pin status, and a short preview."""
        rows = (
            self.db.query(
                ChatSession.session_id,
                ChatSession.created_at,
                ChatSession.parent_session_id,
                ChatSession.title,
                ChatSession.is_pinned,
                func.max(ChatMessage.created_at).label("updated_at"),
                func.count(ChatMessage.id).label("message_count")
            )
            .join(ChatMessage, ChatMessage.session_id == ChatSession.session_id)
            .group_by(ChatSession.id, ChatSession.session_id, ChatSession.created_at, ChatSession.parent_session_id, ChatSession.title, ChatSession.is_pinned)
            .order_by(ChatSession.is_pinned.desc(), func.max(ChatMessage.created_at).desc(), ChatSession.id.desc())
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
            "is_pinned": bool(getattr(row, "is_pinned", 0)),
            "title": row.title or (first_user.get(row.session_id) or "New conversation").strip()[:80],
            "preview": (first_user.get(row.session_id) or "No user message").strip()[:120],
            "message_count": int(row.message_count),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        } for row in rows]

    def pin_session(self, session_id: str, pinned: bool = True) -> bool:
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if not session:
            return False
        session.is_pinned = 1 if pinned else 0
        self.db.commit()
        return True

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
        branch_title = f"Branch · {source_session.title or 'Chat'}"[:200]
        branch = ChatSession(
            session_id=branch_id,
            parent_session_id=session_id,
            branch_from_message_id=anchor.id,
            document_ids=source_session.document_ids or [],
            dataset_id=source_session.dataset_id,
            title=branch_title,
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

    def rename_session(self, session_id: str, title: str) -> bool:
        session = self.db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
        if not session:
            return False
        clean_title = (title or "").strip()[:200]
        if not clean_title:
            return False
        session.title = clean_title
        self.db.commit()
        return True

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

    def chat(self, message: str, dataset_id: int | None = None, dataset_path: str | None = None, symbol: str | None = None, session_id: str | None = None, mode: Literal["auto", "market", "documents", "general"] | None = None, document_ids: list[int] | None = None, chart_period: str | None = None, chart_interval: str | None = None, chart_mode: str | None = None, chart_view: str | None = None, token_callback=None, web_crawl: bool | None = None, model: str | None = None, temperature: float | None = None, max_output_tokens: int | None = None, top_p: float | None = None, top_k: int | None = None, repeat_penalty: float | None = None, seed: int | None = None, custom_persona: str | None = None):
        settings = dict(self._get_settings())
        ai_model = (model.strip() if model and model.strip() else None) or settings.get("ai_model", OLLAMA_MODEL)
        if temperature is not None:
            settings["temperature"] = max(0.0, min(float(temperature), 2.0))
        if max_output_tokens is not None:
            settings["max_output_tokens"] = max(16, min(int(max_output_tokens), 16384))
        if top_p is not None:
            settings["top_p"] = max(0.01, min(float(top_p), 1.0))
        if top_k is not None:
            settings["top_k"] = max(0, min(int(top_k), 1000))
        if repeat_penalty is not None:
            settings["repeat_penalty"] = max(0.0, min(float(repeat_penalty), 5.0))
        if seed is not None:
            settings["seed"] = max(0, min(int(seed), 2147483647))
        if custom_persona is not None:
            settings["custom_persona"] = custom_persona.strip()[:2000]
        
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
        if (not session.title or session.title.strip().lower() in {"new conversation", "new chat"}) and message:
            session.title = generate_conversation_title(message, symbol)
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

        mem_svc = MemoryService(self.db)
        directive = extract_memory_directive(message)
        if directive:
            if directive["action"] in ("remember", "set"):
                saved = mem_svc.set_memory(directive["key"], directive["value"], category=directive.get("category", "preference"))
                answer_text = (
                    f"### Memory Saved\n\n"
                    f"I have saved this to your persistent profile memory:\n"
                    f"- **{saved['key'].replace('_', ' ').title()}**: {saved['value']}\n\n"
                    f"I'll remember this context for future market analysis and research queries."
                )
            elif directive["action"] in ("forget", "delete"):
                target = directive["target"]
                if target.lower() in ("everything", "all", "all memories", "all my memories", "everything about me", "everything you know about me"):
                    mem_svc.clear_memories()
                    answer_text = "### Memories Cleared\n\nI've cleared all persistent profile memories."
                else:
                    mem_svc.delete_memory_by_key(target)
                    answer_text = (
                        f"### Memory Removed\n\n"
                        f"I've removed '{target}' from your persistent profile memory."
                    )
            elif directive["action"] == "clear":
                mem_svc.clear_memories()
                answer_text = "### Memories Cleared\n\nI've cleared all persistent profile memories."
            elif directive["action"] == "list":
                mems = mem_svc.list_memories()
                if mems:
                    mem_list = "\n".join(f"- **{m['key'].replace('_', ' ').title()}** ({m['category']}): {m['value']}" for m in mems)
                    answer_text = (
                        f"### Stored Profile Memories\n\n"
                        f"Here is what I currently have saved in your persistent profile memory:\n\n"
                        f"{mem_list}\n\n"
                        f"You can ask me to update or forget any of these preferences at any time."
                    )
                else:
                    answer_text = "### Stored Profile Memories\n\nI don't have any saved preferences or memories for you yet."
            else:
                answer_text = "Memory preferences updated."

            asst_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=answer_text,
                sources=[],
                metadata_json={"answer_method": "memory_directive", "data_status": "PROCESSED"},
            )
            self.db.add(asst_msg)
            self.db.commit()
            return {
                "session_id": session_id,
                "title": session.title or "New conversation",
                "user_message_id": user_message_id,
                "assistant_message_id": asst_msg.id,
                "answer": answer_text,
                "citations": [],
                "structured_sources": [],
                "data_status": "PROCESSED",
                "answer_method": "memory_directive",
                "model": ai_model,
            }

        if re.search(r"\b(?:what (?:do you remember|is in my memory|are my saved preferences)|show (?:my )?memories)\b", message, re.IGNORECASE):
            mems = mem_svc.list_memories()
            if mems:
                mem_list = "\n".join(f"- **{m['key'].replace('_', ' ').title()}** ({m['category']}): {m['value']}" for m in mems)
                answer_text = (
                    f"### Stored Profile Memories\n\n"
                    f"Here is what I currently have saved in your persistent profile memory:\n\n"
                    f"{mem_list}\n\n"
                    f"You can ask me to update or forget any of these preferences at any time."
                )
            else:
                answer_text = (
                    f"### Stored Profile Memories\n\n"
                    f"I don't have any saved preferences or memories for you yet. "
                    f"You can tell me things like 'remember that I prefer Indian stocks' or 'remember that my investment horizon is 5 years'."
                )
            asst_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=answer_text,
                sources=[],
                metadata_json={"answer_method": "memory_query", "data_status": "PROCESSED"},
            )
            self.db.add(asst_msg)
            self.db.commit()
            return {
                "session_id": session_id,
                "title": session.title or "New conversation",
                "user_message_id": user_message_id,
                "assistant_message_id": asst_msg.id,
                "answer": answer_text,
                "citations": [],
                "structured_sources": [],
                "data_status": "PROCESSED",
                "answer_method": "memory_query",
                "model": ai_model,
            }

        user_memories = mem_svc.get_relevant_memories(message)

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
                web_crawl=web_crawl,
                user_memories=user_memories,
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
                "structured_sources", "duration_seconds",
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
        result["title"] = session.title or "New conversation"
        result["user_message_id"] = user_message_id
        result["assistant_message_id"] = asst_msg.id
        return result
