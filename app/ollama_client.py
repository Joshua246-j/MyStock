"""Small asynchronous Ollama client."""
import httpx
import json

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, EMBEDDING_MODEL


class OllamaError(RuntimeError):
    def __init__(self, message: str, *, code: str = "ai_unavailable", status_code: int = 503):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class OllamaClient:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL.rstrip("/")
        self.model = OLLAMA_MODEL

    async def _post(self, path: str, payload: dict, timeout: float, stream: bool = False):
        try:
            if stream:
                async def stream_generator():
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        async with client.stream("POST", f"{self.base_url}{path}", json=payload) as response:
                            response.raise_for_status()
                            async for line in response.aiter_lines():
                                if line:
                                    yield json.loads(line)
                return stream_generator()
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(f"{self.base_url}{path}", json=payload)
                    response.raise_for_status()
                    return response.json()
        except httpx.ConnectError as exc:
            raise OllamaError("Local AI is unavailable. Start Ollama, then retry your message.", code="ollama_disconnected") from exc
        except httpx.TimeoutException as exc:
            raise OllamaError("Local AI did not respond before the request timeout. Retry or select a smaller model.", code="ollama_timeout", status_code=504) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                model = payload.get("model", self.model)
                raise OllamaError(f"Model '{model}' is not installed in Ollama. Pull it locally or choose an installed model in Settings.", code="ollama_model_missing") from exc
            raise OllamaError(f"Ollama returned HTTP {exc.response.status_code}. Check its service logs and retry.", code="ollama_http_error") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError("Ollama returned an invalid response. Check the local service and retry.", code="ollama_invalid_response") from exc

    @staticmethod
    def _completed_text(result: dict, response_path: str) -> str:
        if result.get("done_reason") == "length" or result.get("done") is False:
            raise OllamaError(
                "The selected model reached its answer-token limit before finishing. Increase Maximum answer tokens in Settings and retry.",
                code="ollama_output_limit",
                status_code=422,
            )
        value = result.get(response_path)
        if response_path == "message":
            value = value.get("content") if isinstance(value, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise OllamaError("Ollama returned an empty response. Retry your request.", code="ollama_empty_response")
        return value

    async def generate(self, prompt: str, system: str = "", model: str = None, *, timeout: float = 30, temperature: float = 0.2, context_size: int = 4096, max_output_tokens: int = 256, stream: bool = False):
        payload = {"model": model or self.model, "prompt": prompt, "system": system, "stream": stream,
                   "options": {"temperature": temperature, "num_ctx": context_size, "num_predict": max_output_tokens}}
        result = await self._post("/api/generate", payload, timeout, stream=stream)
        if stream:
            return result
        return self._completed_text(result, "response")

    async def chat(self, messages: list, model: str = None, *, timeout: float = 30, temperature: float = 0.2, context_size: int = 4096, max_output_tokens: int = 256, stream: bool = False):
        payload = {"model": model or self.model, "messages": messages, "stream": stream,
                   "options": {"temperature": temperature, "num_ctx": context_size, "num_predict": max_output_tokens}}
        result = await self._post("/api/chat", payload, timeout, stream=stream)
        if stream:
            return result
        return self._completed_text(result, "message")

    async def check_health(self, timeout: float = 5):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self.base_url)
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    @staticmethod
    def _supports(item: dict, capability: str) -> bool:
        capabilities = item.get("capabilities")
        if not isinstance(capabilities, list):
            return True
        capabilities = {str(value).casefold() for value in capabilities}
        if capability == "embedding":
            return "embedding" in capabilities
        return bool(capabilities & {"completion", "chat"})

    async def has_model(self, model: str = None, timeout: float = 5, *, capability: str = "generation"):
        selected_model = model or self.model
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                models = response.json().get("models", [])
                return any(
                    (item.get("name") == selected_model or item.get("name", "").startswith(selected_model + ":"))
                    and self._supports(item, capability)
                    for item in models
                )
        except (httpx.HTTPError, ValueError):
            return False

    async def list_models(self, timeout: float = 5):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                names = sorted({
                    str(item.get("name", "")).strip()
                    for item in response.json().get("models", [])
                    if item.get("name") and str(item.get("name", "")).strip() != EMBEDDING_MODEL
                    and self._supports(item, "generation")
                })
                return {"available": True, "models": names, "source": "local_ollama"}
        except (httpx.HTTPError, ValueError) as exc:
            return {"available": False, "models": [], "source": "local_ollama", "error": str(exc)}
