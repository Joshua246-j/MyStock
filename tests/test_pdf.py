import pymupdf as fitz
import os
from app.documents.pdf import PDFLoader
from app.rag.ingest import ingest_document

def test_pdf_processing(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 50), "The company's revenue in FY2025 was $50 billion.")
    
    file_path = tmp_path / "test.pdf"
    doc.save(file_path)
    doc.close()
    
    class MockStore:
        def store(self, texts, metadatas):
            return True
            
    result = ingest_document(PDFLoader(), str(file_path), "test.pdf", 1, MockStore())
    
    assert result["success"] == True
    assert result["pages_processed"] == 1
    assert result["chunks_added"] >= 1
