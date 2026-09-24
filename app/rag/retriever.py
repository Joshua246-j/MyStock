from app.rag.vector_store import get_vector_store

def retrieve_context(query: str, k: int = 5):
    """Retrieves top k most similar chunks for the query."""
    vector_store = get_vector_store()
    try:
        results = vector_store.similarity_search_with_score(query, k=k)
    except Exception as e:
        print(f"Error during retrieval (Ollama down?): {e}")
        return {"context": "", "sources": []}
    
    context_parts = []
    sources = []
    
    for doc, score in results:
        context_parts.append(doc.page_content)
        
        # Format source citation
        metadata = doc.metadata
        source_name = metadata.get("source", "Unknown")
        
        if metadata.get("document_type") == "pdf":
            page = metadata.get("page", "?")
            citation = f"{source_name} — Page {page}"
        elif metadata.get("document_type") == "web":
            url = metadata.get("url", "Unknown URL")
            citation = f"{source_name}\n   {url}"
        else:
            citation = source_name
            
        if citation not in sources:
            sources.append(citation)
            
    return {
        "context": "\n\n---\n\n".join(context_parts),
        "sources": sources
    }
