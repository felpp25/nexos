"""Ingestao e recuperacao: chunks + embeddings guardados no SQLite."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from ..config import settings
from ..db import get_conn, write_conn
from .chunker import chunk_blocks
from .embeddings import embed_query, embed_texts, tokenize
from .extract import extract


def _to_blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def ingest_document(document_id: str, agent_id: str, path: Path, filename: str) -> dict[str, Any]:
    """Extrai, divide, embeda e persiste os chunks de um documento."""
    blocks = extract(path, filename)
    pieces = chunk_blocks(blocks)
    if not pieces:
        raise ValueError("Nenhum conteudo textual utilizavel foi extraido.")

    texts = [p[0] for p in pieces]
    vectors, backend, dim = embed_texts(texts)

    rows = [
        (document_id, agent_id, i, location, text, _to_blob(vector), dim, backend)
        for i, ((text, location), vector) in enumerate(zip(pieces, vectors))
    ]
    with write_conn() as conn:
        conn.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        conn.executemany(
            "INSERT INTO chunks (document_id, agent_id, ordinal, location, text, embedding, dim, backend) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return {
        "chunks": len(rows),
        "chars": sum(len(t) for t in texts),
        "backend": backend,
        "dim": dim,
    }


def _lexical_score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    tokens = set(tokenize(text))
    if not tokens:
        return 0.0
    hits = len(query_tokens & tokens)
    return hits / math.sqrt(len(query_tokens))


def search(agent_id: str, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    """Busca hibrida: cosseno dos embeddings + reforco lexical."""
    top_k = top_k or settings.top_k
    query = (query or "").strip()
    if not query:
        return []

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT c.id, c.text, c.location, c.embedding, c.dim, d.filename, d.id AS document_id "
            "FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE c.agent_id = ? AND d.status = 'ready'",
            (agent_id,),
        ).fetchall()
    if not rows:
        return []

    qvec, _backend, _dim = embed_query(query)
    q = np.asarray(qvec, dtype=np.float32)
    qnorm = float(np.linalg.norm(q)) or 1.0
    query_tokens = set(tokenize(query))

    scored: list[dict[str, Any]] = []
    for row in rows:
        vec = _from_blob(row["embedding"]) if row["embedding"] else np.zeros(0, dtype=np.float32)
        cosine = 0.0
        if vec.size and vec.size == q.size:
            denom = (float(np.linalg.norm(vec)) or 1.0) * qnorm
            cosine = float(np.dot(vec, q) / denom)
        lexical = _lexical_score(query_tokens, row["text"])
        scored.append(
            {
                "chunk_id": row["id"],
                "document_id": row["document_id"],
                "filename": row["filename"],
                "location": row["location"],
                "text": row["text"],
                "score": round(0.75 * cosine + 0.25 * min(lexical, 1.0), 4),
                "cosine": round(cosine, 4),
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    selected: list[dict[str, Any]] = []
    budget = settings.max_context_chars
    for item in scored[: max(top_k * 3, top_k)]:
        if item["score"] <= 0.02 and selected:
            break
        if budget - len(item["text"]) < 0:
            continue
        budget -= len(item["text"])
        selected.append(item)
        if len(selected) >= top_k:
            break
    return selected


def agent_stats(agent_id: str) -> dict[str, int]:
    with get_conn() as conn:
        docs = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(chunks),0) AS c FROM documents "
            "WHERE agent_id=? AND status='ready'",
            (agent_id,),
        ).fetchone()
    return {"documents": int(docs["n"]), "chunks": int(docs["c"])}
