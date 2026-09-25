import pandas as pd
from app.documents.loader import DocumentLoader
from typing import List, Dict, Any

class CSVLoader(DocumentLoader):
    def extract_text(self, file_path: str, filename: str, document_id: int) -> List[Dict[str, Any]]:
        passages = []
        try:
            df = pd.read_csv(file_path)
            for i, row in df.iterrows():
                text = " ".join([f"{col}: {val}" for col, val in row.items()])
                metadata = {
                    "source": filename,
                    "filename": filename,
                    "document_id": document_id or 0,
                    "page": i + 1,
                    "document_type": "dataset"
                }
                passages.append({"text": text, "metadata": metadata})
        except Exception:
            pass
        return passages
