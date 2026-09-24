from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.rag.vector_store import get_vector_store

def chunk_and_store(text: str, metadata: Dict[str, Any]):
    """Splits text into chunks and stores them in ChromaDB with metadata."""
    if not text.strip():
        return False
        
    text_splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=800,
        chunk_overlap=150,
        length_function=len,
        is_separator_regex=False,
    )
    
    chunks = text_splitter.split_text(text)
    
    # We duplicate metadata for each chunk
    metadatas = [metadata for _ in chunks]
    
    vector_store = get_vector_store()
    try:
        vector_store.add_texts(texts=chunks, metadatas=metadatas)
        return True
    except Exception as e:
        print(f"Error adding to vector store (Ollama down?): {e}")
        return False
