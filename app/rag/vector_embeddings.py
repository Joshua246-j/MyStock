from langchain_ollama import OllamaEmbeddings

from app.config import EMBEDDING_MODEL, OLLAMA_BASE_URL


def get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
