import fitz
import os
from app.documents.pdf import process_pdf

from unittest.mock import patch

@patch('app.documents.pdf.chunk_and_store', return_value=True)
def test_pdf_processing(mock_chunk_and_store, tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 50), "The company's revenue in FY2025 was $50 billion.")
    
    file_path = tmp_path / "test.pdf"
    doc.save(file_path)
    doc.close()
    
    result = process_pdf(str(file_path), "test.pdf")
    
    assert result["success"] == True
    assert result["pages_processed"] == 1
    assert result["chunks_added"] >= 1
    mock_chunk_and_store.assert_called()
