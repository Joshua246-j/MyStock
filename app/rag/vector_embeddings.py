from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

from app.config import EMBEDDING_MODEL, OLLAMA_BASE_URL


@lru_cache(maxsize=1)
def get_embeddings() -> OllamaEmbeddings:
    """Reuse the lightweight client wrapper across retrieval operations."""
    return OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
