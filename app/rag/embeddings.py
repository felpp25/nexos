"""Embeddings com dois backends.

- "ollama": usa /api/embed com o modelo configurado (qualidade alta).
- "hash":   vetorizador determinista em Python puro (hashing de tokens +
            trigramas). Nao exige download nenhum, serve como fallback para o
            app funcionar assim que abre.

O backend "auto" (padrao) testa o Ollama uma vez e cai para "hash" se o modelo
de embedding nao estiver instalado.
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
import unicodedata
from threading import Lock
from typing import Sequence

from ..config import settings
from ..llm import OllamaError, client

_state_lock = Lock()
_resolved: dict[str, object] = {}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "a", "o", "os", "as", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "um", "uma", "para", "por", "com", "que", "se", "ao", "aos",
    "the", "of", "and", "to", "in", "is", "it", "for", "on", "as", "at", "by",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(normalize(text)) if len(t) > 1 and t not in _STOPWORDS]


# --------------------------------------------------------------- hash backend
def _bucket(token: str, dim: int) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return struct.unpack("<Q", digest)[0] % dim


def hash_embed_one(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    tokens = tokenize(text)
    for tok in tokens:
        vec[_bucket(tok, dim)] += 1.0
        for i in range(len(tok) - 2):
            vec[_bucket("#" + tok[i : i + 3], dim)] += 0.35
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


# ------------------------------------------------------------ backend resolver
def resolve_backend(force_refresh: bool = False) -> str:
    """Decide qual backend usar; o resultado fica em cache no processo."""
    with _state_lock:
        if not force_refresh and "backend" in _resolved:
            return str(_resolved["backend"])

        configured = (settings.embed_backend or "auto").lower()
        backend = "hash"
        if configured == "ollama":
            backend = "ollama"
        elif configured == "auto":
            try:
                if client.has_model(settings.embed_model):
                    client.embed(["teste"])
                    backend = "ollama"
            except (OllamaError, Exception):  # noqa: BLE001
                backend = "hash"
        _resolved["backend"] = backend
        return backend


def backend_info() -> dict[str, object]:
    backend = resolve_backend()
    return {
        "backend": backend,
        "model": settings.embed_model if backend == "ollama" else f"hash-{settings.hash_dim}",
        "quality": "alta" if backend == "ollama" else "basica",
        "hint": ""
        if backend == "ollama"
        else f"Para busca semantica de alta qualidade rode: ollama pull {settings.embed_model}",
    }


def embed_texts(texts: Sequence[str]) -> tuple[list[list[float]], str, int]:
    """Retorna (vetores, backend, dimensao)."""
    texts = list(texts)
    if not texts:
        return [], resolve_backend(), 0

    backend = resolve_backend()
    if backend == "ollama":
        try:
            vectors: list[list[float]] = []
            for i in range(0, len(texts), 16):
                vectors.extend(client.embed(texts[i : i + 16]))
            if vectors and len(vectors) == len(texts):
                return vectors, "ollama", len(vectors[0])
        except Exception:  # noqa: BLE001 - degrada para hash sem quebrar ingestao
            with _state_lock:
                _resolved["backend"] = "hash"
            backend = "hash"

    dim = settings.hash_dim
    return [hash_embed_one(t, dim) for t in texts], "hash", dim


def embed_query(text: str) -> tuple[list[float], str, int]:
    vectors, backend, dim = embed_texts([text])
    return (vectors[0] if vectors else []), backend, dim
