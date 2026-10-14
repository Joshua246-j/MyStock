import logging
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.rag.lexical_store import clean_orphaned_chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stockrag.rebuild")

if __name__ == "__main__":
    logger.info("Starting RAG index reconciliation...")
    deleted = clean_orphaned_chunks()
    if deleted > 0:
        logger.info(f"Cleaned {deleted} orphaned rows and refreshed vector store.")
    else:
        logger.info("No orphaned chunks found. Index is healthy.")
