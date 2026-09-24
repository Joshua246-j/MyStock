from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from app.config import OLLAMA_BASE_URL, EMBEDDING_MODEL, CHROMA_PATH

def get_embeddings():
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL
    )

def get_vector_store():
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=get_embeddings()
    )
