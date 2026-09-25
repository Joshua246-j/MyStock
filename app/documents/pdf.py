import pymupdf as fitz
from app.documents.loader import DocumentLoader
from typing import List, Dict, Any

class PDFLoader(DocumentLoader):
    def extract_text(self, file_path: str, filename: str, document_id: int) -> List[Dict[str, Any]]:
        passages = []
        try:
            doc = fitz.open(file_path)
            if len(doc) == 0:
                return passages
                
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text")
                
                if text.strip():
                    metadata = {
                        "source": filename,
                        "filename": filename,
                        "document_id": document_id or 0,
                        "page": page_num + 1,
                        "document_type": "pdf"
                    }
                    passages.append({"text": text, "metadata": metadata})
            return passages
        except Exception:
            return passages
