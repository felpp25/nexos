"""CRUD de agentes."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..db import get_conn, new_id, now, write_conn
from ..rag.store import agent_stats

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = ""
    observations: str = ""
    prompt_override: str = ""
    use_master: bool = True
    model: str = ""
    temperature: float = Field(default=settings.temperature, ge=0.0, le=2.0)
    top_k: int = Field(default=settings.top_k, ge=0, le=20)


class AgentPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    purpose: Optional[str] = None
    observations: Optional[str] = None
    prompt_override: Optional[str] = None
    use_master: Optional[bool] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_k: Optional[int] = Field(default=None, ge=0, le=20)
    status: Optional[str] = None


def _serialize(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["use_master"] = bool(data.get("use_master", 1))
    data.update(agent_stats(data["id"]))
    return data


def fetch_agent(agent_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Agente nao encontrado")
    return dict(row)


@router.get("")
def list_agents(status: str = "all") -> dict[str, Any]:
    query = "SELECT * FROM agents"
    params: tuple = ()
    if status in ("active", "archived"):
        query += " WHERE status=?"
        params = (status,)
    query += " ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, LOWER(name)"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return {"agents": [_serialize(r) for r in rows]}


@router.post("", status_code=201)
def create_agent(payload: AgentIn) -> dict[str, Any]:
    agent_id = new_id()
    stamp = now()
    with write_conn() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, purpose, observations, prompt_override, use_master, "
            "model, temperature, top_k, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                agent_id,
                payload.name.strip(),
                payload.purpose.strip(),
                payload.observations.strip(),
                payload.prompt_override.strip(),
                int(payload.use_master),
                payload.model.strip(),
                payload.temperature,
                payload.top_k,
                stamp,
                stamp,
            ),
        )
    return _serialize(fetch_agent(agent_id))


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    return _serialize(fetch_agent(agent_id))


@router.put("/{agent_id}")
def update_agent(agent_id: str, payload: AgentPatch) -> dict[str, Any]:
    fetch_agent(agent_id)
    fields = payload.model_dump(exclude_none=True)
    if "status" in fields and fields["status"] not in ("active", "archived"):
        raise HTTPException(status_code=400, detail="status deve ser 'active' ou 'archived'")
    if "use_master" in fields:
        fields["use_master"] = int(bool(fields["use_master"]))
    for key in ("name", "purpose", "observations", "prompt_override", "model"):
        if key in fields and isinstance(fields[key], str):
            fields[key] = fields[key].strip()
    if not fields:
        return _serialize(fetch_agent(agent_id))

    fields["updated_at"] = now()
    assignments = ", ".join(f"{k}=?" for k in fields)
    with write_conn() as conn:
        conn.execute(
            f"UPDATE agents SET {assignments} WHERE id=?", (*fields.values(), agent_id)
        )
    return _serialize(fetch_agent(agent_id))


@router.post("/{agent_id}/archive")
def archive_agent(agent_id: str) -> dict[str, Any]:
    return update_agent(agent_id, AgentPatch(status="archived"))


@router.post("/{agent_id}/restore")
def restore_agent(agent_id: str) -> dict[str, Any]:
    return update_agent(agent_id, AgentPatch(status="active"))


@router.delete("/{agent_id}")
def delete_agent(agent_id: str) -> dict[str, str]:
    fetch_agent(agent_id)
    with get_conn() as conn:
        stored = [
            r["stored_name"]
            for r in conn.execute(
                "SELECT stored_name FROM documents WHERE agent_id=?", (agent_id,)
            ).fetchall()
        ]
    with write_conn() as conn:
        conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    for name in stored:
        path = settings.uploads_dir / name
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    return {"status": "deleted", "id": agent_id}
