"""Small asynchronous Ollama client."""
import httpx
import json
import asyncio
import time

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, EMBEDDING_MODEL

_MODEL_CATALOG_TTL_SECONDS = 5.0
_MODEL_CATALOG_CACHE: dict[tuple[int, str], tuple[float, dict]] = {}
_MODEL_CATALOG_PENDING: dict[tuple[int, str], asyncio.Task] = {}


def _copy_catalog(catalog: dict) -> dict:
    return {**catalog, "models": list(catalog.get("models", [])), "embedding_models": list(catalog.get("embedding_models", []))}


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
                    try:
                        async with httpx.AsyncClient(timeout=timeout) as client:
                            async with client.stream("POST", f"{self.base_url}{path}", json=payload) as response:
                                response.raise_for_status()
                                async for line in response.aiter_lines():
                                    if line:
                                        yield json.loads(line)
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
        if isinstance(value, str) and value.strip():
            return value
        raise OllamaError("Ollama returned an empty response. Retry your request.", code="ollama_empty_response")

    async def generate(self, prompt: str, system: str = "", model: str = None, *, timeout: float = 60, temperature: float = 0.2, context_size: int = 4096, max_output_tokens: int = 2048, stream: bool = False, top_p: float = 0.9, top_k: int = 40, repeat_penalty: float = 1.1, seed: int = 0):
        payload = {"model": model or self.model, "prompt": prompt, "system": system, "stream": stream, "keep_alive": "10m",
                   "options": {"temperature": temperature, "num_ctx": context_size, "num_predict": max_output_tokens, "top_p": top_p, "top_k": top_k, "repeat_penalty": repeat_penalty, "seed": seed}}
        result = await self._post("/api/generate", payload, timeout, stream=stream)
        if stream:
            return result
        return self._completed_text(result, "response")

    async def chat(self, messages: list, model: str = None, *, timeout: float = 60, temperature: float = 0.2, context_size: int = 4096, max_output_tokens: int = 2048, stream: bool = False, top_p: float = 0.9, top_k: int = 40, repeat_penalty: float = 1.1, seed: int = 0):
        payload = {"model": model or self.model, "messages": messages, "stream": stream, "keep_alive": "10m",
                   "options": {"temperature": temperature, "num_ctx": context_size, "num_predict": max_output_tokens, "top_p": top_p, "top_k": top_k, "repeat_penalty": repeat_penalty, "seed": seed}}
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
    def _is_embedding_model(item: dict) -> bool:
        capabilities = item.get("capabilities")
        if isinstance(capabilities, list):
            return "embedding" in {str(value).casefold() for value in capabilities} and not OllamaClient._supports(item, "generation")
        name = str(item.get("name") or item.get("model") or "").casefold()
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        family = str(details.get("family") or "").casefold()
        return any(marker in name or marker in family for marker in ("embed", "nomic-bert", "snowflake-arctic-embed", "all-minilm", "bge-m3"))

    @staticmethod
    def _supports(item: dict, capability: str) -> bool:
        capabilities = item.get("capabilities")
        if not isinstance(capabilities, list):
            name = str(item.get("name") or item.get("model") or "").casefold()
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            family = str(details.get("family") or "").casefold()
            embedding_only = any(marker in name or marker in family for marker in ("embed", "nomic-bert", "snowflake-arctic-embed", "all-minilm", "bge-m3"))
            return embedding_only if capability == "embedding" else not embedding_only
        capabilities = {str(value).casefold() for value in capabilities}
        if capability == "embedding":
            return "embedding" in capabilities
        return bool(capabilities & {"completion", "chat"})

    async def has_model(self, model: str = None, timeout: float = 5, *, capability: str = "generation"):
        selected_model = model or self.model
        catalog = await self.list_models(timeout)
        names = catalog.get("embedding_models" if capability == "embedding" else "models", [])
        return catalog.get("available") is True and any(name == selected_model or name.startswith(selected_model + ":") for name in names)

    async def list_running_models(self, timeout: float = 3):
        """Return models currently resident in Ollama, separately from installed models."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{self.base_url}/api/ps")
                response.raise_for_status()
                items = response.json().get("models", [])
                names = sorted({str(item.get("name") or item.get("model") or "").strip()
                                for item in items if isinstance(item, dict)})
                return {"available": True, "models": [name for name in names if name]}
        except (httpx.HTTPError, ValueError) as exc:
            return {"available": False, "models": [], "error": str(exc)}

    async def list_models(self, timeout: float = 5):
        cache_key = (id(asyncio.get_running_loop()), self.base_url)
        cached = _MODEL_CATALOG_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < _MODEL_CATALOG_TTL_SECONDS:
            return _copy_catalog(cached[1])
        pending = _MODEL_CATALOG_PENDING.get(cache_key)
        if pending is None:
            pending = asyncio.create_task(self._fetch_model_catalog(timeout))
            _MODEL_CATALOG_PENDING[cache_key] = pending
            pending.add_done_callback(
                lambda task: _MODEL_CATALOG_PENDING.pop(cache_key, None)
                if _MODEL_CATALOG_PENDING.get(cache_key) is task else None
            )
        # A caller timing out must not cancel the in-flight fetch shared by
        # other requests. The HTTP request itself still has its own timeout.
        result = await asyncio.shield(pending)
        return _copy_catalog(result)

    async def _fetch_model_catalog(self, timeout: float) -> dict:
        cache_key = (id(asyncio.get_running_loop()), self.base_url)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                catalog = [item for item in response.json().get("models", []) if item.get("name")]
                names = sorted({str(item.get("name", "")).strip() for item in catalog if self._supports(item, "generation")})
                embeddings = sorted({str(item.get("name", "")).strip() for item in catalog if self._supports(item, "embedding")})
                result = {"available": True, "models": names, "embedding_models": embeddings, "source": "local_ollama"}
                _MODEL_CATALOG_CACHE[cache_key] = (time.monotonic(), result)
                return _copy_catalog(result)
        except (httpx.HTTPError, ValueError) as exc:
            return {"available": False, "models": [], "embedding_models": [], "source": "local_ollama", "error": str(exc)}
