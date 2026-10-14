import asyncio
import logging
import json
from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session
from app.db.database import get_db, SessionLocal
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
    chart_period: Literal["1mo", "3mo", "6mo", "1y", "2y", "5y"] | None = None
    chart_interval: Literal["1d", "1wk", "1mo"] | None = None
    chart_mode: Literal["line", "candlestick"] | None = None
    chart_view: Literal["price", "volume", "trend", "bollinger", "rsi", "macd", "atr", "performance"] | None = None
    web_crawl: bool | None = None
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    top_k: int | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    custom_persona: str | None = Field(default=None, max_length=2000)

class BranchRequest(BaseModel):
    message_id: int = Field(gt=0)


@router.post("/chat/sessions/{session_id}/branch")
def branch_chat_session(session_id: str, req: BranchRequest, chat_service: ChatService = Depends(get_chat_service)):
    try:
        return chat_service.branch_session(session_id, req.message_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str, chat_service: ChatService = Depends(get_chat_service)):
    session = chat_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session

class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

@router.put("/chat/sessions/{session_id}/rename")
def rename_chat_session(session_id: str, req: RenameRequest, chat_service: ChatService = Depends(get_chat_service)):
    if not chat_service.rename_session(session_id, req.title):
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"renamed": True, "session_id": session_id, "title": req.title}

class PinRequest(BaseModel):
    pinned: bool | None = None
    is_pinned: bool | int | None = None

    def get_pinned(self) -> bool:
        if self.pinned is not None:
            return bool(self.pinned)
        if self.is_pinned is not None:
            return bool(self.is_pinned)
        return True

@router.put("/chat/sessions/{session_id}/pin")
def pin_chat_session(session_id: str, req: PinRequest, chat_service: ChatService = Depends(get_chat_service)):
    pinned_val = req.get_pinned()
    if not chat_service.pin_session(session_id, pinned_val):
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"pinned": pinned_val, "session_id": session_id}

@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(session_id: str, chat_service: ChatService = Depends(get_chat_service)):
    if not chat_service.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Chat session not found")
    return {"deleted": True, "session_id": session_id}

@router.get("/chat/sessions")
def list_chat_sessions(limit: int = 50, chat_service: ChatService = Depends(get_chat_service)):
    return {"sessions": chat_service.list_sessions(limit)}

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
            document_ids=req.document_ids,
            chart_period=req.chart_period,
            chart_interval=req.chart_interval,
            chart_mode=req.chart_mode,
            chart_view=req.chart_view,
            web_crawl=req.web_crawl,
            model=req.model,
            temperature=req.temperature,
            max_output_tokens=req.max_output_tokens,
            top_p=req.top_p,
            top_k=req.top_k,
            repeat_penalty=req.repeat_penalty,
            seed=req.seed,
            custom_persona=req.custom_persona,
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
        "title": result.get("title"),
        "user_message_id": result.get("user_message_id"),
        "assistant_message_id": result.get("assistant_message_id"),
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


@router.post("/chat/stream")
async def stream_chat(req: ChatRequest):
    """Stream generated tokens while preserving the same retrieval and persistence path."""
    loop = asyncio.get_running_loop()
    events: asyncio.Queue = asyncio.Queue()

    def emit(event: str, payload: dict):
        loop.call_soon_threadsafe(events.put_nowait, (event, payload))

    def run_chat():
        try:
            with SessionLocal() as db:
                result = ChatService(db).chat(
                    message=req.message,
                    dataset_id=req.dataset_id,
                    dataset_path=req.dataset_path,
                    symbol=req.symbol,
                    session_id=req.session_id,
                    mode=req.mode,
                    document_ids=req.document_ids,
                    chart_period=req.chart_period,
                    chart_interval=req.chart_interval,
                    chart_mode=req.chart_mode,
                    chart_view=req.chart_view,
                    token_callback=lambda token: emit("token", {"text": token}),
                    web_crawl=req.web_crawl,
                    model=req.model,
                    temperature=req.temperature,
                    max_output_tokens=req.max_output_tokens,
                    top_p=req.top_p,
                    top_k=req.top_k,
                    repeat_penalty=req.repeat_penalty,
                    seed=req.seed,
                    custom_persona=req.custom_persona,
                )
            emit("done", {
                "session_id": result["session_id"],
                "title": result.get("title"),
                "user_message_id": result.get("user_message_id"),
                "assistant_message_id": result.get("assistant_message_id"),
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
                "data_status": result.get("data_status"),
            })
        except OllamaError as exc:
            emit("error", {"code": exc.code, "message": str(exc), "status_code": exc.status_code})
        except ValueError as exc:
            emit("error", {"code": "invalid_chat_request", "message": str(exc), "status_code": 422})
        except Exception:
            logger.exception("streaming_chat_orchestration_failed")
            emit("error", {"code": "chat_analysis_failed", "message": "The analysis service failed before it could produce a complete answer. Please retry.", "status_code": 500})
        finally:
            emit("complete", {})

    worker = asyncio.create_task(asyncio.to_thread(run_chat))

    async def event_stream():
        try:
            while True:
                try:
                    event, payload = await asyncio.wait_for(events.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": processing\n\n"
                    continue
                if event == "complete":
                    break
                yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
            await worker
        except (asyncio.CancelledError, GeneratorExit):
            worker.cancel()
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
