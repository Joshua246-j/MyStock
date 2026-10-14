import asyncio
import uuid
import json
import re
from hashlib import sha256
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.config import UPLOAD_DIR
from app.db.database import get_db, SessionLocal
from app.db.models import DocumentMetadata, UserSettings
from app.documents.pdf import PDFLoader
from app.documents.text import HTMLLoader, TextLoader
from app.documents.word import WordLoader
from app.rag.ingest import ingest_document
from app.analysis.data_analysis import analyze_dataset
from app.web.crawler import crawl_url

router = APIRouter(tags=["Documents & Data"])
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

class CrawlRequest(BaseModel):
    url: str
    ticker: str | None = Field(default=None, max_length=20, pattern=r"^[A-Za-z0-9.^=_-]{1,20}$")

async def _store_upload(file: UploadFile) -> tuple[Path, str]:
    filename = Path(file.filename or "upload").name
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 25 MB upload limit")
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    path = Path(UPLOAD_DIR) / safe_name
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, contents)
    return path, filename


def _create_document_record(filename: str, document_type: str, storage_path: str | None = None, metadata: dict | None = None) -> int:
    with SessionLocal() as db:
        record = DocumentMetadata(filename=filename, document_type=document_type, status="processing", storage_path=storage_path, metadata_json=metadata or {})
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id


def _find_document_by_hash(content_hash: str) -> int | None:
    with SessionLocal() as db:
        for row in db.query(DocumentMetadata).filter(DocumentMetadata.status.in_(["processing", "completed"])).all():
            if (row.metadata_json or {}).get("content_hash") == content_hash:
                return row.id
    return None


def _set_document_status(document_id: int, status: str, filename: str | None = None, metadata: dict | None = None) -> None:
    with SessionLocal() as db:
        record = db.query(DocumentMetadata).filter(DocumentMetadata.id == document_id).first()
        if record:
            record.status = status
            if filename:
                record.filename = filename
            if metadata:
                record.metadata_json = {**(record.metadata_json or {}), **metadata}
            db.commit()


def _parse_upload_metadata(raw: str | None, document_format: str, filename: str) -> dict:
    try:
        supplied = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Document metadata must be valid JSON.") from exc
    if not isinstance(supplied, dict):
        raise HTTPException(status_code=400, detail="Document metadata must be a JSON object.")
    allowed = {"company", "ticker", "exchange", "country", "sector", "industry", "source_type", "document_type", "source_url", "title", "published_at", "filing_date", "period_start", "period_end", "language", "section"}
    if supplied.keys() - allowed:
        raise HTTPException(status_code=400, detail="Document metadata contains unsupported fields.")
    metadata = {}
    for key, value in supplied.items():
        if value is None or value == "":
            continue
        if not isinstance(value, str) or len(value) > 500:
            raise HTTPException(status_code=400, detail=f"Metadata field '{key}' must be a string of at most 500 characters.")
        value = value.strip()
        if key == "ticker":
            if not re.fullmatch(r"[A-Za-z0-9.^=_-]{1,20}", value):
                raise HTTPException(status_code=400, detail="Ticker metadata contains unsupported characters.")
            value = value.upper()
        metadata[key] = value
    metadata.setdefault("source_type", "user_upload")
    metadata.setdefault("document_type", document_format)
    metadata.setdefault("title", filename)
    metadata["format"] = document_format
    return metadata


def _get_request_settings() -> dict:
    with SessionLocal() as db:
        row = db.query(UserSettings).first()
        return row.settings if row and row.settings else {}


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    records = db.query(DocumentMetadata).order_by(DocumentMetadata.uploaded_at.desc()).all()
    return {"documents": [{"id": row.id, "filename": row.filename, "type": row.document_type, "status": row.status, "uploaded_at": row.uploaded_at.isoformat(), "metadata": row.metadata_json or {}} for row in records]}

@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    record = db.query(DocumentMetadata).filter(DocumentMetadata.id == document_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Document not found")
    if record.storage_path:
        try:
            path = Path(record.storage_path)
            if path.exists():
                path.unlink()
        except Exception:
            pass
    # Clean up associated lexical chunks and vector embeddings
    from app.rag.lexical_store import delete_document_chunks
    try:
        delete_document_chunks(document_id)
    except Exception:
        pass
    db.delete(record)
    db.commit()
    return {"message": "Document deleted successfully"}


@router.post("/upload/pdf")
@router.post("/upload/document")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    metadata_json: str | None = Form(None)
):
    extension = Path(file.filename or "").suffix.lower()
    formats = {".pdf": "pdf", ".txt": "txt", ".html": "html", ".htm": "html", ".docx": "docx"}
    document_format = formats.get(extension)
    if not document_format:
        raise HTTPException(status_code=400, detail="Supported research documents are PDF, DOCX, TXT, and HTML.")
    file_path, original_name = await _store_upload(file)
    file_bytes = await asyncio.to_thread(file_path.read_bytes)
    if document_format == "pdf" and not file_bytes.startswith(b"%PDF-"):
        await asyncio.to_thread(file_path.unlink, missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file does not contain a valid PDF signature.")
    metadata = _parse_upload_metadata(metadata_json, document_format, original_name)
    metadata["content_hash"] = sha256(file_bytes).hexdigest()
    duplicate_id = await asyncio.to_thread(_find_document_by_hash, metadata["content_hash"])
    if duplicate_id:
        await asyncio.to_thread(file_path.unlink, missing_ok=True)
        return {"message": "This exact document is already indexed.", "document_id": duplicate_id, "duplicate": True}
    document_id = await asyncio.to_thread(_create_document_record, original_name, document_format, str(file_path.resolve()), metadata)
    
    def process_document():
        loader = PDFLoader() if document_format == "pdf" else HTMLLoader() if document_format == "html" else WordLoader() if document_format == "docx" else TextLoader()
        result = ingest_document(loader, str(file_path), original_name, document_id, None, metadata)
        _set_document_status(document_id, "completed" if result.get("success") else "failed")

    background_tasks.add_task(asyncio.to_thread, process_document)
    return {"message": "Document processing started", "document_id": document_id, "status": "processing"}

@router.post("/upload/dataset")
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    metadata_json: str | None = Form(None)
):
    if not (file.filename or "").lower().endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed")
    file_path, original_name = await _store_upload(file)
    metadata = _parse_upload_metadata(metadata_json, "dataset", original_name)
    metadata["content_hash"] = sha256(await asyncio.to_thread(file_path.read_bytes)).hexdigest()
    document_id = await asyncio.to_thread(_create_document_record, original_name, "dataset", str(file_path.resolve()), metadata)
    
    def process_dataset():
        result = analyze_dataset(str(file_path), "")
        _set_document_status(document_id, "completed" if result.get("success") else "failed")

    background_tasks.add_task(asyncio.to_thread, process_dataset)
    return {"message": "Dataset processing started", "document_id": document_id, "status": "processing"}

@router.post("/crawl")
async def crawl_web(req: CrawlRequest, background_tasks: BackgroundTasks):
    if not req.url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")
        
    settings = await asyncio.to_thread(_get_request_settings)
    if not settings.get("web_research_enabled", True):
        raise HTTPException(status_code=403, detail="Web research is disabled in settings")
    timeout = max(1, min(float(settings.get("request_timeout", 30)), 180))
    document_id = await asyncio.to_thread(_create_document_record, req.url, "web", None, {"source_type": "web", "source_url": req.url, "title": req.url})
    hints = {"ticker": req.ticker.upper()} if req.ticker else None
    
    def process_crawl():
        result = crawl_url(req.url, timeout, document_id, hints)
        if not result.get("success"):
            _set_document_status(document_id, "failed")
        else:
            _set_document_status(document_id, "completed", result.get("title"), result.get("metadata"))

    background_tasks.add_task(asyncio.to_thread, process_crawl)
    return {"message": "URL crawling started", "document_id": document_id, "status": "processing"}
