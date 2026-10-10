from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from app.documents.loader import DocumentExtractionError, DocumentLoader


class TextLoader(DocumentLoader):
    def extract_text(self, file_path: str, filename: str, document_id: int) -> list[dict[str, Any]]:
        try:
            raw = Path(file_path).read_bytes()
            if b"\x00" in raw:
                raise DocumentExtractionError("The text file contains binary data.")
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError("Text files must use UTF-8 encoding.") from exc
        if not text.strip():
            return []
        return [{"text": text, "metadata": {
            "source": filename, "filename": filename, "document_id": document_id,
            "document_type": "txt",
        }}]


class HTMLLoader(DocumentLoader):
    def extract_text(self, file_path: str, filename: str, document_id: int) -> list[dict[str, Any]]:
        try:
            raw = Path(file_path).read_bytes()
            html = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError("HTML files must use UTF-8 encoding.") from exc
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else filename
        for element in soup.select("script, style, noscript, template, svg, iframe"):
            element.decompose()
        text = soup.get_text("\n", strip=True)
        if not text:
            return []
        return [{"text": text, "metadata": {
            "source": filename, "filename": filename, "document_id": document_id,
            "document_type": "html", "title": title,
        }}]
