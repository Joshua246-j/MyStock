import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.config import UPLOAD_DIR
from app.documents.pdf import process_pdf
from app.analysis.data_analysis import analyze_dataset
from app.web.crawler import crawl_url

router = APIRouter(tags=["Documents & Data"])

class CrawlRequest(BaseModel):
    url: str

@router.post("/upload/pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    result = process_pdf(file_path, file.filename)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
        
    return {"message": "PDF uploaded and indexed successfully", "details": result}

@router.post("/upload/dataset")
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed")
        
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    result = analyze_dataset(file_path, "test")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=f"Invalid dataset: {result.get('error')}")
        
    return {"message": "Dataset uploaded successfully", "dataset_path": file_path, "columns": result.get("columns")}

@router.post("/crawl")
async def crawl_web(req: CrawlRequest):
    if not req.url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")
        
    result = crawl_url(req.url)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
        
    return {"message": "URL crawled and indexed successfully", "title": result.get("title")}
