"""Conversas e chat com streaming (SSE)."""
from __future__ import annotations

import json
from typing import Any, Iterator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import settings
from ..db import dumps, get_conn, get_master_prompt, new_id, now, write_conn
from ..llm import OllamaError, client
from ..prompts import compose_system_prompt
from ..rag.store import search

router = APIRouter(tags=["chat"])


class ChatIn(BaseModel):
    agent_id: str
    message: str = Field(min_length=1)
    conversation_id: Optional[str] = None


def _get_agent(agent_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Agente nao encontrado")
    return dict(row)


def _ensure_conversation(agent_id: str, conversation_id: Optional[str], first_message: str) -> str:
    if conversation_id:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE id=? AND agent_id=?",
                (conversation_id, agent_id),
            ).fetchone()
        if row is not None:
            return conversation_id
    conversation_id = new_id()
    title = first_message.strip().replace("\n", " ")[:60] or "Nova conversa"
    stamp = now()
    with write_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (id, agent_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, agent_id, title, stamp, stamp),
        )
    return conversation_id


def _history(conversation_id: str, limit: int) -> list[dict[str, str]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _save_message(conversation_id: str, role: str, content: str, sources: list[dict]) -> None:
    stamp = now()
    with write_conn() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, sources, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, dumps(sources), stamp),
        )
        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (stamp, conversation_id))


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/chat")
def chat(payload: ChatIn) -> StreamingResponse:
    agent = _get_agent(payload.agent_id)
    if agent["status"] != "active":
        raise HTTPException(status_code=400, detail="Este agente esta arquivado.")

    conversation_id = _ensure_conversation(
        payload.agent_id, payload.conversation_id, payload.message
    )
    history = _history(conversation_id, settings.history_turns * 2)
    _save_message(conversation_id, "user", payload.message, [])

    top_k = int(agent.get("top_k") or settings.top_k)
    passages = search(payload.agent_id, payload.message, top_k) if top_k else []
    sources = [
        {
            "n": i,
            "filename": p["filename"],
            "location": p["location"],
            "score": p["score"],
            "document_id": p["document_id"],
            "excerpt": p["text"][:280],
        }
        for i, p in enumerate(passages, start=1)
    ]

    system_prompt = compose_system_prompt(agent, get_master_prompt(), passages)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": payload.message})

    model = (agent.get("model") or "").strip() or settings.ollama_model
    temperature = float(agent.get("temperature") if agent.get("temperature") is not None else settings.temperature)

    def stream() -> Iterator[str]:
        yield _sse("meta", {"conversation_id": conversation_id, "sources": sources, "model": model})
        buffer: list[str] = []
        try:
            for token in client.chat_stream(messages, model=model, temperature=temperature):
                buffer.append(token)
                yield _sse("token", {"t": token})
        except OllamaError as exc:
            _save_message(conversation_id, "assistant", "".join(buffer), sources)
            yield _sse("error", {"message": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            _save_message(conversation_id, "assistant", "".join(buffer), sources)
            yield _sse("error", {"message": f"Falha inesperada: {exc}"})
            return
        _save_message(conversation_id, "assistant", "".join(buffer), sources)
        yield _sse("done", {"conversation_id": conversation_id})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/agents/{agent_id}/conversations")
def list_conversations(agent_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.updated_at, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS messages "
            "FROM conversations c WHERE c.agent_id=? ORDER BY c.updated_at DESC LIMIT 50",
            (agent_id,),
        ).fetchall()
    return {"conversations": [dict(r) for r in rows]}


@router.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id=?", (conversation_id,)
        ).fetchone()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversa nao encontrada")
        rows = conn.execute(
            "SELECT role, content, sources, created_at FROM messages "
            "WHERE conversation_id=? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    messages = []
    for r in rows:
        item = dict(r)
        try:
            item["sources"] = json.loads(item["sources"] or "[]")
        except json.JSONDecodeError:
            item["sources"] = []
        messages.append(item)
    return {"conversation": dict(conv), "messages": messages}


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, str]:
    with write_conn() as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada")
    return {"status": "deleted", "id": conversation_id}
