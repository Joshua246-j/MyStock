from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from app.config import OLLAMA_BASE_URL, EMBEDDING_MODEL, CHROMA_PATH
from threading import Lock

_vector_store: Chroma | None = None
_vector_store_lock = Lock()

def get_embeddings():
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL
    )

def get_vector_store():
    """Return one process-wide Chroma client; concurrent constructors corrupt Rust client state."""
    global _vector_store
    if _vector_store is None:
        with _vector_store_lock:
            if _vector_store is None:
                _vector_store = Chroma(
                    persist_directory=CHROMA_PATH,
                    embedding_function=get_embeddings(),
                )
    return _vector_store
