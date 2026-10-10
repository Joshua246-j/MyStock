from abc import ABC, abstractmethod
from typing import List, Dict, Any


class DocumentExtractionError(RuntimeError):
    """A supported file could not be safely converted into searchable text."""

class DocumentLoader(ABC):
    @abstractmethod
    def extract_text(self, file_path: str, filename: str, document_id: int) -> List[Dict[str, Any]]:
        """Extracts text and returns a list of dictionaries with 'text' and 'metadata' keys."""
        pass
