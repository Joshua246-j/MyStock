import os
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import ChatSession, ChatMessage, UserSettings
from app.analysis.orchestrator import orchestrate_chat

router = APIRouter(tags=["Chat"])

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    dataset_path: str | None = None
    symbol: str | None = None
    session_id: str | None = None
    mode: str | None = "auto"


@router.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at, ChatMessage.id).all()
    return {"session_id": session_id, "messages": [{"role": row.role, "content": row.content, "created_at": row.created_at.isoformat()} for row in messages]}

@router.post("/chat")
async def chat(req: ChatRequest, db: Session = Depends(get_db)):
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    # Get settings
    settings_record = db.query(UserSettings).first()
    settings = settings_record.settings if settings_record else {}
    ai_model = settings.get("ai_model", "gemma3:4b")

    # Handle session
    session_id = req.session_id
    if not session_id:
        session_id = str(uuid.uuid4())
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        session = ChatSession(session_id=session_id)
        db.add(session)
        db.commit()

    # Get history
    history = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at, ChatMessage.id).all()
    formatted_history = [{"role": msg.role, "content": msg.content} for msg in history]

    # Save user message
    user_msg = ChatMessage(session_id=session_id, role="user", content=req.message)
    db.add(user_msg)
    db.commit()

    result = await orchestrate_chat(
        message=req.message,
        symbol=req.symbol,
        dataset_path=req.dataset_path,
        history=formatted_history,
        model=ai_model,
        settings=settings,
    )
    
    # Save assistant message
    asst_msg = ChatMessage(session_id=session_id, role="assistant", content=result["answer"], sources=result["citations"])
    db.add(asst_msg)
    db.commit()

    return {
        "session_id": session_id,
        "answer": result["answer"],
        "structured_analysis": result["structured_analysis"],
        "citations": result["citations"],
        "data_timestamp": result["data_timestamp"],
        "model": result["model"],
        "retrieval": result["retrieval"],
        "sources_unverified": result["sources_unverified"],
        "data_status": result["data_status"]
    }
