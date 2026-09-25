from typing import List, Dict, Any
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.rag.vector_store import get_vector_store
from app.rag.lexical_store import index_chunks, index_chunks_batch
from app.rag.interfaces import IRetrieverStore
from app.documents.loader import DocumentLoader

logger = logging.getLogger("stockrag.rag")

class DefaultRetrieverStore(IRetrieverStore):
    def store(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> bool:
        if not texts:
            return False
            
        lexical_count = 0
        try:
            lexical_count = index_chunks_batch(texts, metadatas)
        except Exception as e:
            logger.exception("rag_lexical_ingest_failed", extra={"reason": str(e)})

        try:
            vector_store = get_vector_store()
            vector_store.add_texts(texts=texts, metadatas=metadatas)
            return True
        except Exception as e:
            if lexical_count:
                logger.warning("rag_semantic_index_unavailable", extra={"reason": str(e), "lexical_chunks": lexical_count})
                return True
            logger.exception("rag_ingest_failed", extra={"reason": str(e)})
            return False

def ingest_document(loader: DocumentLoader, file_path: str, filename: str, document_id: int, store: IRetrieverStore = None):
    store = store or DefaultRetrieverStore()
    passages = loader.extract_text(file_path, filename, document_id)
    if not passages:
        return {"success": False, "error": "The document contained no indexable text.", "chunks_added": 0}
        
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=800,
        chunk_overlap=150,
        length_function=len,
        is_separator_regex=False,
    )
    
    all_chunks = []
    all_metadatas = []
    
    for passage in passages:
        text = passage["text"]
        metadata = passage["metadata"]
        chunks = text_splitter.split_text(text)
        all_chunks.extend(chunks)
        all_metadatas.extend([metadata for _ in chunks])
        
    if store.store(all_chunks, all_metadatas):
        return {"success": True, "pages_processed": len(passages), "chunks_added": len(all_chunks)}
    return {"success": False, "error": "Failed to store document in retriever store.", "chunks_added": 0}

# For backward compatibility / existing usages if any remain
def chunk_and_store(text: str, metadata: Dict[str, Any]):
    store = DefaultRetrieverStore()
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=800,
        chunk_overlap=150,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_text(text)
    if chunks:
        return store.store(chunks, [metadata for _ in chunks])
    return False
