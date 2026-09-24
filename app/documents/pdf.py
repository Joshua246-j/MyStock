import fitz  # PyMuPDF
import os
from app.rag.ingest import chunk_and_store

def process_pdf(file_path: str, original_filename: str):
    """Extracts text from PDF page by page and stores in RAG."""
    try:
        doc = fitz.open(file_path)
        if len(doc) == 0:
            return {"success": False, "error": "Empty PDF"}
            
        chunks_added = 0
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            
            if text.strip():
                metadata = {
                    "source": original_filename,
                    "filename": original_filename,
                    "page": page_num + 1,
                    "document_type": "pdf"
                }
                if chunk_and_store(text, metadata):
                    chunks_added += 1
                    
        return {"success": True, "pages_processed": len(doc), "chunks_added": chunks_added}
    except Exception as e:
        return {"success": False, "error": str(e)}
