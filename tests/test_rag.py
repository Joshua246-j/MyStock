import pytest
from app.rag.ingest import chunk_and_store
from app.rag.retriever import retrieve_context

from unittest.mock import patch, MagicMock

@patch('app.rag.ingest.get_vector_store')
@patch('app.rag.retriever.get_vector_store')
def test_rag_ingest_and_retrieve(mock_retriever_vs, mock_ingest_vs):
    # Mocking the vector store behavior
    mock_vs_instance = MagicMock()
    mock_ingest_vs.return_value = mock_vs_instance
    mock_retriever_vs.return_value = mock_vs_instance
    
    # Mock retrieval results
    class MockDoc:
        def __init__(self, content, metadata):
            self.page_content = content
            self.metadata = metadata
            
    mock_vs_instance.similarity_search_with_score.return_value = [
        (MockDoc("The secret password is 'OpenSesame123'.", {"source": "test_source", "document_type": "pdf", "page": 1}), 0.9)
    ]
    
    metadata = {"source": "test_source", "document_type": "pdf", "page": 1}
    success = chunk_and_store("The secret password is 'OpenSesame123'.", metadata)
    assert success == True
    
    context = retrieve_context("What is the password?", k=1)
    
    assert "OpenSesame123" in context["context"]
    assert "test_source — Page 1" in context["sources"]
