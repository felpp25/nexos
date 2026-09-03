"""Status do sistema, primeira execucao (setup) e prompt mestre."""
from __future__ import annotations

import json
import webbrowser
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import settings
from ..db import get_conn, get_master_prompt, set_setting
from ..llm import OllamaError, client
from ..prompts import DEFAULT_MASTER_PROMPT, compose_system_prompt
from ..rag.embeddings import backend_info, resolve_backend

router = APIRouter(prefix="/api", tags=["system"])


class MasterPromptIn(BaseModel):
    prompt: str


class PreviewIn(BaseModel):
    prompt: str | None = None
    agent_id: str | None = None


@router.get("/health")
def health() -> dict[str, Any]:
    ollama = client.health()
    with get_conn() as conn:
        agents = conn.execute(
            "SELECT COUNT(*) AS n FROM agents WHERE status='active'"
        ).fetchone()["n"]
        docs = conn.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE status='ready'"
        ).fetchone()["n"]
        chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    return {
        "ollama": ollama,
        "model": settings.ollama_model,
        "embeddings": backend_info(),
        "counts": {"agents": agents, "documents": docs, "chunks": chunks},
    }


@router.post("/embeddings/refresh")
def refresh_embeddings() -> dict[str, Any]:
    resolve_backend(force_refresh=True)
    return backend_info()


@router.get("/master-prompt")
def read_master_prompt() -> dict[str, str]:
    return {"prompt": get_master_prompt(), "default": DEFAULT_MASTER_PROMPT}


@router.put("/master-prompt")
def write_master_prompt(payload: MasterPromptIn) -> dict[str, str]:
    prompt = payload.prompt.strip() or DEFAULT_MASTER_PROMPT
    set_setting("master_prompt", prompt)
    return {"prompt": prompt}


@router.post("/master-prompt/reset")
def reset_master_prompt() -> dict[str, str]:
    set_setting("master_prompt", DEFAULT_MASTER_PROMPT)
    return {"prompt": DEFAULT_MASTER_PROMPT}


@router.post("/master-prompt/preview")
def preview_master_prompt(payload: PreviewIn) -> dict[str, str]:
    """Mostra como o system prompt final fica para um agente real."""
    agent: dict[str, Any] = {
        "name": "Agente de exemplo",
        "purpose": "responder duvidas sobre a base de conhecimento",
        "observations": "tom formal, respostas curtas",
        "prompt_override": "",
        "use_master": 1,
    }
    if payload.agent_id:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM agents WHERE id=?", (payload.agent_id,)).fetchone()
        if row is not None:
            agent = dict(row)
    master = payload.prompt if payload.prompt is not None else get_master_prompt()
    passages = [
        {
            "filename": "exemplo.pdf",
            "location": "pagina 4",
            "text": "(trecho recuperado da base de conhecimento aparece aqui)",
        }
    ]
    return {"preview": compose_system_prompt(agent, master, passages)}


# --------------------------------------------------------------------- setup
LINKS = {
    "ollama_download": settings.ollama_download_url,
    "ollama_model": settings.ollama_model_url,
}


class PullIn(BaseModel):
    model: str | None = None


class OpenLinkIn(BaseModel):
    target: str


@router.get("/setup")
def setup_status() -> dict[str, Any]:
    """Tudo que a tela de primeira execucao precisa saber."""
    ollama = client.health()
    required = settings.ollama_model
    has_model = any(
        m == required or m.split(":")[0] == required.split(":")[0]
        for m in ollama.get("models", [])
    )
    return {
        "ollama_online": ollama["online"],
        "ollama_url": ollama["url"],
        "models": ollama.get("models", []),
        "required_model": required,
        "has_required_model": has_model,
        "ready": bool(ollama["online"] and has_model),
        "links": LINKS,
        "pull_command": f"ollama pull {required}",
    }


@router.post("/open-link")
def open_link(payload: OpenLinkIn) -> dict[str, str]:
    """Abre um link oficial no navegador padrao (lista fixa, sem URL livre)."""
    url = LINKS.get(payload.target)
    if not url:
        raise HTTPException(status_code=400, detail="Link desconhecido")
    webbrowser.open(url)
    return {"opened": url}


@router.post("/models/pull")
def pull_model(payload: PullIn) -> StreamingResponse:
    """Baixa o modelo pelo proprio Ollama, transmitindo o progresso (SSE)."""
    model = (payload.model or settings.ollama_model).strip()

    def stream() -> Iterator[str]:
        def sse(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield sse("start", {"model": model})
        try:
            for chunk in client.pull_stream(model):
                total = chunk.get("total") or 0
                completed = chunk.get("completed") or 0
                percent = round(completed / total * 100, 1) if total else None
                yield sse(
                    "progress",
                    {
                        "status": chunk.get("status", ""),
                        "total": total,
                        "completed": completed,
                        "percent": percent,
                    },
                )
        except OllamaError as exc:
            yield sse("error", {"message": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            yield sse("error", {"message": f"Falha ao baixar o modelo: {exc}"})
            return
        yield sse("done", {"model": model})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
