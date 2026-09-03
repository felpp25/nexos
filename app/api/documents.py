"""Upload e gestao dos documentos da base de conhecimento."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import settings
from ..db import get_conn, new_id, now, write_conn
from ..rag.extract import SUPPORTED, kind_of
from ..rag.store import ingest_document

router = APIRouter(tags=["documents"])


def _agent_exists(agent_id: str) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM agents WHERE id=?", (agent_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Agente nao encontrado")


def _process(document_id: str, agent_id: str, stored_name: str, filename: str) -> None:
    path = settings.uploads_dir / stored_name
    try:
        result = ingest_document(document_id, agent_id, path, filename)
        with write_conn() as conn:
            conn.execute(
                "UPDATE documents SET status='ready', chunks=?, chars=?, error='' WHERE id=?",
                (result["chunks"], result["chars"], document_id),
            )
    except Exception as exc:  # noqa: BLE001 - erro precisa aparecer na UI
        with write_conn() as conn:
            conn.execute(
                "UPDATE documents SET status='error', error=? WHERE id=?",
                (str(exc)[:500], document_id),
            )


@router.post("/api/agents/{agent_id}/documents", status_code=201)
async def upload_documents(
    agent_id: str,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    _agent_exists(agent_id)
    created: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    max_bytes = settings.max_upload_mb * 1024 * 1024

    for upload in files:
        filename = Path(upload.filename or "arquivo").name
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED:
            rejected.append({"filename": filename, "reason": f"extensao {ext or '?'} nao suportada"})
            await upload.close()
            continue

        document_id = new_id()
        stored_name = f"{document_id}{ext}"
        target = settings.uploads_dir / stored_name
        with target.open("wb") as fh:
            shutil.copyfileobj(upload.file, fh, length=1024 * 1024)
        await upload.close()

        size = target.stat().st_size
        if size > max_bytes:
            target.unlink(missing_ok=True)
            rejected.append(
                {"filename": filename, "reason": f"acima de {settings.max_upload_mb} MB"}
            )
            continue

        with write_conn() as conn:
            conn.execute(
                "INSERT INTO documents (id, agent_id, filename, stored_name, kind, size_bytes, "
                "status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'processing', ?)",
                (document_id, agent_id, filename, stored_name, kind_of(filename), size, now()),
            )
        background.add_task(_process, document_id, agent_id, stored_name, filename)
        created.append({"id": document_id, "filename": filename, "status": "processing"})

    return {"created": created, "rejected": rejected}


@router.get("/api/agents/{agent_id}/documents")
def list_documents(agent_id: str) -> dict[str, Any]:
    _agent_exists(agent_id)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, kind, size_bytes, chars, chunks, status, error, created_at "
            "FROM documents WHERE agent_id=? ORDER BY created_at DESC",
            (agent_id,),
        ).fetchall()
    return {"documents": [dict(r) for r in rows]}


@router.get("/api/documents/{document_id}/file")
def download_document(document_id: str) -> FileResponse:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT filename, stored_name FROM documents WHERE id=?", (document_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    path = settings.uploads_dir / row["stored_name"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo ausente no disco")
    return FileResponse(path, filename=row["filename"])


@router.post("/api/documents/{document_id}/reprocess")
def reprocess_document(document_id: str, background: BackgroundTasks) -> dict[str, str]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    with write_conn() as conn:
        conn.execute(
            "UPDATE documents SET status='processing', error='' WHERE id=?", (document_id,)
        )
    background.add_task(
        _process, document_id, row["agent_id"], row["stored_name"], row["filename"]
    )
    return {"status": "processing", "id": document_id}


@router.delete("/api/documents/{document_id}")
def delete_document(document_id: str) -> dict[str, str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT stored_name FROM documents WHERE id=?", (document_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")
    with write_conn() as conn:
        conn.execute("DELETE FROM documents WHERE id=?", (document_id,))
    path = settings.uploads_dir / row["stored_name"]
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    return {"status": "deleted", "id": document_id}
