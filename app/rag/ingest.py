from typing import List, Dict, Any
import logging
from datetime import datetime, timezone
from hashlib import sha256
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.rag.vector_store import get_vector_store
from app.rag.lexical_store import index_chunks, index_chunks_batch_with_ids
from app.rag.interfaces import IRetrieverStore
from app.documents.loader import DocumentLoader
from app.documents.loader import DocumentExtractionError

logger = logging.getLogger("stockrag.rag")

class DefaultRetrieverStore(IRetrieverStore):
    def store(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> bool:
        if not texts:
            return False
            
        lexical_count = 0
        try:
            chunk_ids = index_chunks_batch_with_ids(texts, metadatas)
            lexical_count = len(chunk_ids)
        except Exception as e:
            logger.exception("rag_lexical_ingest_failed", extra={"reason": str(e)})

        try:
            vector_store = get_vector_store()
            vector_store.add_texts(texts=texts, metadatas=metadatas, chunk_ids=chunk_ids)
            return True
        except Exception as e:
            if lexical_count:
                logger.warning("rag_semantic_index_unavailable", extra={"reason": str(e), "lexical_chunks": lexical_count})
                return True
            logger.exception("rag_ingest_failed", extra={"reason": str(e)})
            return False

def ingest_document(loader: DocumentLoader, file_path: str, filename: str, document_id: int, store: IRetrieverStore = None, document_metadata: Dict[str, Any] | None = None):
    store = store or DefaultRetrieverStore()
    try:
        passages = loader.extract_text(file_path, filename, document_id)
    except DocumentExtractionError as exc:
        logger.warning("document_extraction_failed", extra={"document_id": document_id, "filename": filename, "reason": str(exc)})
        return {"success": False, "error": str(exc), "chunks_added": 0}
    if not passages:
        return {"success": False, "error": "The document contained no indexable text.", "chunks_added": 0}
        
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        # Slightly larger passages reduce embedding round trips on long filings
        # while keeping enough overlap to preserve paragraph-boundary context.
        chunk_size=1200,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )
    
    all_chunks = []
    all_metadatas = []
    
    chunk_index = 0
    timestamp = datetime.now(timezone.utc).isoformat()
    for passage in passages:
        text = passage["text"]
        passage_metadata = passage.get("metadata") or {}
        supplied_metadata = document_metadata or {}
        metadata = {**passage_metadata, **supplied_metadata}
        extracted_title = passage_metadata.get("title")
        if extracted_title and supplied_metadata.get("title") in (None, filename):
            metadata["title"] = extracted_title
        metadata.setdefault("document_id", document_id)
        metadata.setdefault("filename", filename)
        metadata.setdefault("source", filename)
        metadata.setdefault("source_type", "web" if metadata.get("document_type") == "web" else "user_upload")
        metadata.setdefault("document_type", "pdf")
        metadata.setdefault("title", filename)
        metadata.setdefault("source_url", metadata.get("url"))
        metadata.setdefault("created_at", timestamp)
        metadata["updated_at"] = timestamp
        chunks = text_splitter.split_text(text)
        all_chunks.extend(chunks)
        for chunk in chunks:
            chunk_metadata = {
                **{key: value for key, value in metadata.items() if value is not None},
                "chunk_id": f"{document_id}:{chunk_index}",
                "chunk_index": chunk_index,
                "content_hash": sha256(chunk.encode("utf-8")).hexdigest(),
            }
            all_metadatas.append(chunk_metadata)
            chunk_index += 1
        
    if store.store(all_chunks, all_metadatas):
        return {"success": True, "pages_processed": len(passages), "chunks_added": len(all_chunks)}
    return {"success": False, "error": "Failed to store document in retriever store.", "chunks_added": 0}

# For backward compatibility / existing usages if any remain
def chunk_and_store(text: str, metadata: Dict[str, Any]):
    store = DefaultRetrieverStore()
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=1200,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_text(text)
    if chunks:
        return store.store(chunks, [metadata for _ in chunks])
    return False
