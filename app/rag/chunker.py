"""Divisao de texto em chunks com sobreposicao, respeitando paragrafos."""
from __future__ import annotations

import re
from typing import Iterable

from ..config import settings

_WS_RE = re.compile(r"[ \t ]+")
_NL_RE = re.compile(r"\n{3,}")


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _hard_split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    size = size or settings.chunk_size
    overlap = overlap if overlap is not None else settings.chunk_overlap
    text = clean(text)
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    buffer = ""
    for para in _split_paragraphs(text):
        if len(para) > size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_hard_split(para, size))
            continue
        if not buffer:
            buffer = para
        elif len(buffer) + len(para) + 2 <= size:
            buffer = f"{buffer}\n\n{para}"
        else:
            chunks.append(buffer)
            buffer = para
    if buffer:
        chunks.append(buffer)

    if overlap <= 0 or len(chunks) < 2:
        return chunks

    overlapped: list[str] = [chunks[0]]
    for prev, current in zip(chunks, chunks[1:]):
        tail = prev[-overlap:]
        overlapped.append(f"{tail}\n{current}" if tail else current)
    return overlapped


def chunk_blocks(blocks: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Recebe (texto, localizacao) e devolve (chunk, localizacao)."""
    out: list[tuple[str, str]] = []
    for text, location in blocks:
        for chunk in chunk_text(text):
            if chunk.strip():
                out.append((chunk.strip(), location))
    return out
