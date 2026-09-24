import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma")
UPLOAD_DIR = "./uploads"

# Create necessary directories
os.makedirs(CHROMA_PATH, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs("./data/documents", exist_ok=True)
os.makedirs("./data/datasets", exist_ok=True)
os.makedirs("./data/web", exist_ok=True)
