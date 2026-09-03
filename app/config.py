"""Configuracao central do NEXOS (carrega .env quando presente).

Funciona em dois modos:
- desenvolvimento: raiz = pasta do projeto, dados em ./data
- executavel (PyInstaller): assets vem do bundle, dados vao para
  %LOCALAPPDATA%\\NEXOS (ou NEXOS_DATA_DIR, se definida)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = APP_DIR

ROOT = APP_DIR


def _default_data_dir() -> Path:
    override = os.environ.get("NEXOS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if FROZEN:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "NEXOS"
    return APP_DIR / "data"


def _load_env_file() -> None:
    for env in (APP_DIR / ".env", _default_data_dir() / ".env"):
        if not env.exists():
            continue
        for raw in env.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def _str(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


class Settings:
    # Ollama
    ollama_url: str = _str("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = _str("OLLAMA_MODEL", "qwen2.5:3b")
    temperature: float = _float("TEMPERATURE", 0.3)
    num_ctx: int = _int("NUM_CTX", 8192)
    request_timeout: float = _float("REQUEST_TIMEOUT", 600.0)

    # Embeddings: "ollama" usa EMBED_MODEL via API; "hash" e o fallback offline.
    embed_backend: str = _str("EMBED_BACKEND", "auto")
    embed_model: str = _str("EMBED_MODEL", "nomic-embed-text")
    hash_dim: int = _int("HASH_DIM", 512)

    # RAG
    chunk_size: int = _int("CHUNK_SIZE", 1100)
    chunk_overlap: int = _int("CHUNK_OVERLAP", 180)
    top_k: int = _int("TOP_K", 5)
    max_context_chars: int = _int("MAX_CONTEXT_CHARS", 9000)
    history_turns: int = _int("HISTORY_TURNS", 8)

    # Servidor
    host: str = _str("HOST", "127.0.0.1")
    port: int = _int("PORT", 8770)

    # Caminhos
    data_dir: Path = _default_data_dir()
    uploads_dir: Path = _default_data_dir() / "uploads"
    db_path: Path = _default_data_dir() / "nexos.db"
    web_dir: Path = BUNDLE_DIR / "web"

    max_upload_mb: int = _int("MAX_UPLOAD_MB", 60)

    # Links oficiais (usados na tela de primeira execucao)
    ollama_download_url: str = "https://ollama.com/download"
    ollama_model_url: str = "https://ollama.com/library/qwen2.5"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
