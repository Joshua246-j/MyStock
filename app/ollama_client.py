import httpx
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

class OllamaClient:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.model = OLLAMA_MODEL

    def generate(self, prompt: str, system: str = "", model: str = None, *, timeout: float = 30, temperature: float = 0.2, context_size: int = 4096):
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": context_size},
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                return response.json().get("response", "")
        except httpx.ConnectError:
            return "Error: Could not connect to Ollama. Is it running?"
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 return f"Error: Model '{model or self.model}' not found. Please run 'ollama pull {model or self.model}'"
            return f"Error: Ollama API returned status {e.response.status_code}"
        except Exception as e:
            return f"Error communicating with Ollama: {str(e)}"
            
    def chat(self, messages: list, model: str = None, *, timeout: float = 30, temperature: float = 0.2, context_size: int = 4096):
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": context_size},
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                return response.json().get("message", {}).get("content", "")
        except httpx.ConnectError:
            return "Error: Could not connect to Ollama. Is it running?"
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 return f"Error: Model '{model or self.model}' not found. Please run 'ollama pull {model or self.model}'"
            return f"Error: Ollama API returned status {e.response.status_code}"
        except Exception as e:
            return f"Error communicating with Ollama: {str(e)}"
            
    def check_health(self, timeout: float = 5):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(self.base_url)
                return response.status_code == 200
        except Exception:
            return False
            
    def has_model(self, model: str = None, timeout: float = 5):
        selected_model = model or self.model
        url = f"{self.base_url}/api/tags"
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url)
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    return any(m.get("name") == selected_model or m.get("name", "").startswith(selected_model + ":") for m in models)
            return False
        except Exception:
            return False
