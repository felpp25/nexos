"""Cliente Ollama: chat com streaming, embeddings e status."""
from __future__ import annotations

import json
from typing import Any, Iterator, Optional, Sequence

import httpx

from .config import settings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.ollama_model

    # ---------------------------------------------------------------- status
    def health(self) -> dict[str, Any]:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=4.0)
            r.raise_for_status()
            models = [m.get("name", "") for m in r.json().get("models", [])]
            return {"online": True, "models": models, "url": self.base_url}
        except Exception as exc:  # noqa: BLE001 - status nunca deve derrubar a UI
            return {"online": False, "models": [], "url": self.base_url, "error": str(exc)}

    def has_model(self, name: str) -> bool:
        info = self.health()
        if not info["online"]:
            return False
        wanted = name.split(":")[0]
        return any(m == name or m.split(":")[0] == wanted for m in info["models"])

    # ------------------------------------------------------------------ chat
    def chat_stream(
        self,
        messages: Sequence[dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        num_ctx: Optional[int] = None,
    ) -> Iterator[str]:
        payload = {
            "model": model or self.model,
            "messages": list(messages),
            "stream": True,
            "options": {
                "temperature": settings.temperature if temperature is None else temperature,
                "num_ctx": num_ctx or settings.num_ctx,
            },
        }
        timeout = httpx.Timeout(settings.request_timeout, connect=10.0)
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as r:
                if r.status_code >= 400:
                    detail = r.read().decode("utf-8", "replace")[:400]
                    raise OllamaError(f"Ollama respondeu {r.status_code}: {detail}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        raise OllamaError(str(obj["error"]))
                    chunk = (obj.get("message") or {}).get("content", "")
                    if chunk:
                        yield chunk
                    if obj.get("done"):
                        return

    def chat(self, messages: Sequence[dict[str, str]], **kwargs: Any) -> str:
        return "".join(self.chat_stream(messages, **kwargs))

    # ------------------------------------------------------------- download
    def pull_stream(self, model: str) -> Iterator[dict[str, Any]]:
        """Baixa um modelo via Ollama, emitindo o progresso linha a linha."""
        payload = {"model": model, "stream": True}
        timeout = httpx.Timeout(None, connect=15.0)
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", f"{self.base_url}/api/pull", json=payload) as r:
                if r.status_code >= 400:
                    detail = r.read().decode("utf-8", "replace")[:300]
                    raise OllamaError(f"Ollama respondeu {r.status_code}: {detail}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        raise OllamaError(str(obj["error"]))
                    yield obj


    # ------------------------------------------------------------ embeddings
    def embed(self, texts: Sequence[str], model: Optional[str] = None) -> list[list[float]]:
        model = model or settings.embed_model
        payload = {"model": model, "input": list(texts)}
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            r = client.post(f"{self.base_url}/api/embed", json=payload)
            if r.status_code >= 400:
                raise OllamaError(
                    f"Falha ao gerar embeddings com '{model}' ({r.status_code}). "
                    f"Rode: ollama pull {model}"
                )
            data = r.json()
        vectors = data.get("embeddings") or []
        if not vectors:
            raise OllamaError("Ollama retornou embeddings vazios.")
        return vectors


client = OllamaClient()
