import pymupdf as fitz
import shutil
from app.documents.loader import DocumentLoader
from app.documents.loader import DocumentExtractionError
from typing import List, Dict, Any

class PDFLoader(DocumentLoader):
    def extract_text(self, file_path: str, filename: str, document_id: int) -> List[Dict[str, Any]]:
        passages = []
        try:
            doc = fitz.open(file_path)
            if len(doc) == 0:
                raise DocumentExtractionError("The PDF has no pages.")
            if doc.needs_pass:
                raise DocumentExtractionError("The PDF is password protected and cannot be indexed.")
            tesseract_available = shutil.which("tesseract") is not None
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text("text")
                ocr_used = False
                if not text.strip() and page.get_images(full=True):
                    if not tesseract_available:
                        raise DocumentExtractionError(
                            f"Page {page_num + 1} appears to be scanned. Install Tesseract OCR and retry."
                        )
                    try:
                        text = page.get_text("text", textpage=page.get_textpage_ocr(language="eng", dpi=200, full=True))
                    except Exception as exc:
                        raise DocumentExtractionError(f"OCR failed on PDF page {page_num + 1}: {exc}") from exc
                    ocr_used = True
                    if len(text.strip()) < 20:
                        raise DocumentExtractionError(f"OCR produced too little readable text on page {page_num + 1}.")
                
                if text.strip():
                    metadata = {
                        "source": filename,
                        "filename": filename,
                        "document_id": document_id or 0,
                        "page": page_num + 1,
                        "document_type": "pdf",
                        "ocr_used": ocr_used,
                    }
                    passages.append({"text": text, "metadata": metadata})
            return passages
        except DocumentExtractionError:
            raise
        except Exception as exc:
            raise DocumentExtractionError(f"Could not read PDF: {exc}") from exc
