import asyncio
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.config import UPLOAD_DIR
from app.db.database import get_db, SessionLocal
from app.db.models import DocumentMetadata, UserSettings
from app.documents.pdf import PDFLoader
from app.rag.ingest import ingest_document
from app.analysis.data_analysis import analyze_dataset
from app.web.crawler import crawl_url

router = APIRouter(tags=["Documents & Data"])
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

class CrawlRequest(BaseModel):
    url: str

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


def _create_document_record(filename: str, document_type: str, storage_path: str | None = None) -> int:
    with SessionLocal() as db:
        record = DocumentMetadata(filename=filename, document_type=document_type, status="processing", storage_path=storage_path)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id


def _set_document_status(document_id: int, status: str, filename: str | None = None) -> None:
    with SessionLocal() as db:
        record = db.query(DocumentMetadata).filter(DocumentMetadata.id == document_id).first()
        if record:
            record.status = status
            if filename:
                record.filename = filename
            db.commit()


def _get_request_settings() -> dict:
    with SessionLocal() as db:
        row = db.query(UserSettings).first()
        return row.settings if row and row.settings else {}


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    records = db.query(DocumentMetadata).order_by(DocumentMetadata.uploaded_at.desc()).all()
    return {"documents": [{"id": row.id, "filename": row.filename, "type": row.document_type, "status": row.status, "uploaded_at": row.uploaded_at.isoformat()} for row in records]}


@router.post("/upload/pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    file_path, original_name = await _store_upload(file)
    document_id = await asyncio.to_thread(_create_document_record, original_name, "pdf", str(file_path.resolve()))
    loader = PDFLoader()
    result = await asyncio.to_thread(ingest_document, loader, str(file_path), original_name, document_id)
    await asyncio.to_thread(_set_document_status, document_id, "completed" if result.get("success") else "failed")
    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("error", "PDF indexing failed"))
        
    return {"message": "PDF uploaded and indexed successfully", "document_id": document_id, "details": result}

@router.post("/upload/dataset")
async def upload_dataset(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed")
    file_path, original_name = await _store_upload(file)
    document_id = await asyncio.to_thread(_create_document_record, original_name, "dataset", str(file_path.resolve()))
    result = await asyncio.to_thread(analyze_dataset, str(file_path), "")
    await asyncio.to_thread(_set_document_status, document_id, "completed" if result.get("success") else "failed")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=f"Invalid dataset: {result.get('error')}")
        
    return {"message": "Dataset uploaded successfully", "document_id": document_id, "columns": result.get("columns")}

@router.post("/crawl")
async def crawl_web(req: CrawlRequest):
    if not req.url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")
        
    settings = await asyncio.to_thread(_get_request_settings)
    if not settings.get("web_research_enabled", True):
        raise HTTPException(status_code=403, detail="Web research is disabled in settings")
    timeout = max(1, min(float(settings.get("request_timeout", 30)), 180))
    document_id = await asyncio.to_thread(_create_document_record, req.url, "web")
    result = await asyncio.to_thread(crawl_url, req.url, timeout, document_id)
    if not result.get("success"):
        await asyncio.to_thread(_set_document_status, document_id, "failed")
        raise HTTPException(status_code=422, detail=result.get("error"))
    await asyncio.to_thread(_set_document_status, document_id, "completed", result.get("title"))
        
    return {"message": "URL crawled and indexed successfully", "title": result.get("title"), "document_id": document_id}
