import asyncio

from fastapi import APIRouter

from app.ollama_client import OllamaClient

router = APIRouter(prefix="/models", tags=["AI Models"])
client = OllamaClient()


@router.get("")
async def get_models():
    """Return only models installed on this machine; no cloud/free-model claims."""
    try:
        result = await asyncio.wait_for(client.list_models(5), timeout=6)
        return result
    except asyncio.TimeoutError:
        return {"available": False, "models": [], "source": "local_ollama", "error": "Local model service timed out."}
