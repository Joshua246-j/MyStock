import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")
    
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:1.5b"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    UPSTOX_ACCESS_TOKEN: str = ""
    FINNHUB_API_KEY: str = ""
    
    CHROMA_PATH: str = "data/chroma"
    UPLOAD_DIR: str = "uploads"
    
    @field_validator("CHROMA_PATH", "UPLOAD_DIR", mode="before")
    @classmethod
    def make_absolute_path(cls, v: str) -> str:
        if not v:
            return v
        path = Path(v)
        return str(path if path.is_absolute() else PROJECT_ROOT / path)

settings = Settings()

OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
OLLAMA_MODEL = settings.OLLAMA_MODEL
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
UPSTOX_ACCESS_TOKEN = settings.UPSTOX_ACCESS_TOKEN
FINNHUB_API_KEY = settings.FINNHUB_API_KEY
CHROMA_PATH = settings.CHROMA_PATH
UPLOAD_DIR = settings.UPLOAD_DIR

# Create necessary directories
os.makedirs(CHROMA_PATH, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROJECT_ROOT / "data" / "documents", exist_ok=True)
os.makedirs(PROJECT_ROOT / "data" / "datasets", exist_ok=True)
os.makedirs(PROJECT_ROOT / "data" / "web", exist_ok=True)
