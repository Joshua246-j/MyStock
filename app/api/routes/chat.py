import asyncio
import logging
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from pathlib import Path
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.chat import ChatService
from app.ollama_client import OllamaError

def get_chat_service(db: Session = Depends(get_db)):
    return ChatService(db)

router = APIRouter(tags=["Chat"])
logger = logging.getLogger("stockrag.chat")

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    dataset_path: str | None = None
    symbol: str | None = None
    session_id: str | None = None
    mode: Literal["auto", "market", "documents", "general"] | None = None
    document_ids: list[int] | None = None
    dataset_id: int | None = None


@router.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str, chat_service: ChatService = Depends(get_chat_service)):
    session = chat_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session

@router.post("/chat")
def chat(req: ChatRequest, chat_service: ChatService = Depends(get_chat_service)):
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
        
    try:
        result = chat_service.chat(
            message=req.message,
            dataset_id=req.dataset_id,
            dataset_path=req.dataset_path,
            symbol=req.symbol,
            session_id=req.session_id,
            mode=req.mode,
            document_ids=req.document_ids
        )
    except ValueError as e:
        if "outside the upload directory" in str(e) or "Use a stored dataset ID" in str(e):
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))
    except OllamaError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    except Exception as exc:
        logger.exception("chat_orchestration_failed")
        raise HTTPException(status_code=500, detail={"code": "chat_analysis_failed", "message": "The analysis service failed before it could produce an answer. Please retry."}) from exc
        
    return {
        "session_id": result["session_id"],
        "answer": result["answer"],
        "structured_analysis": result.get("structured_analysis"),
        "citations": result.get("citations"),
        "data_timestamp": result.get("data_timestamp"),
        "model": result.get("model"),
        "retrieval": result.get("retrieval"),
        "sources_unverified": result.get("sources_unverified"),
        "format_unverified": result.get("format_unverified"),
        "numeric_validation": result.get("numeric_validation"),
        "answer_method": result.get("answer_method"),
        "data_status": result.get("data_status")
    }
