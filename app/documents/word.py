from typing import Any

from docx import Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.text.paragraph import Paragraph
from docx.table import Table

from app.documents.loader import DocumentExtractionError, DocumentLoader


class WordLoader(DocumentLoader):
    """Extract paragraphs and tables from modern .docx files with section labels."""

    def extract_text(self, file_path: str, filename: str, document_id: int) -> list[dict[str, Any]]:
        try:
            document = Document(file_path)
        except Exception as exc:
            raise DocumentExtractionError(f"Could not read Word document: {exc}") from exc

        passages = []
        section = None
        for element in document.element.body.iterchildren():
            if isinstance(element, CT_P):
                paragraph = Paragraph(element, document)
                text = paragraph.text.strip()
                if not text:
                    continue
                if paragraph.style and paragraph.style.name.startswith("Heading"):
                    section = text[:500]
                passages.append((text, section))
            elif isinstance(element, CT_Tbl):
                table = Table(element, document)
                rows = [" | ".join(cell.text.strip().replace("\n", " ") for cell in row.cells) for row in table.rows]
                text = "\n".join(row for row in rows if row.strip())
                if text:
                    passages.append((text, section))

        if not passages:
            return []
        return [{"text": text, "metadata": {
            "source": filename,
            "filename": filename,
            "document_id": document_id,
            "document_type": "docx",
            **({"section": section} if section else {}),
        }} for text, section in passages]
