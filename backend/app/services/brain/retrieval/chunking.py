"""Deterministic text chunking with stable section references.

Each chunk keeps a ``section_ref`` (the source segment label, e.g. ``"synopsis"``
or ``"panel 3 · dialogue"``) and char offsets, so a retrieved hit can be cited
back to a precise location. Hashing is content-based so re-indexing re-embeds
ONLY chunks whose text actually changed.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_index: int
    content: str
    section_ref: str
    char_start: int
    char_end: int
    content_hash: str
    token_estimate: int


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def chunk_text(
    text: str, *, label: str, start_index: int, chunk_chars: int, overlap: int
) -> list[Chunk]:
    """Split one labelled segment into overlapping windows. Short segments stay a
    single chunk keyed by the bare label; long ones get ``"<label> · part N"``."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        windows = [(0, len(text))]
    else:
        windows = []
        step = max(1, chunk_chars - max(0, overlap))
        pos = 0
        while pos < len(text):
            end = min(len(text), pos + chunk_chars)
            windows.append((pos, end))
            if end >= len(text):
                break
            pos += step
    multi = len(windows) > 1
    out: list[Chunk] = []
    for i, (start, end) in enumerate(windows):
        body = text[start:end].strip()
        if not body:
            continue
        ref = f"{label} · part {i + 1}" if multi else label
        out.append(
            Chunk(
                chunk_index=start_index + len(out),
                content=body,
                section_ref=ref,
                char_start=start,
                char_end=end,
                content_hash=content_hash(body),
                token_estimate=max(1, len(body) // 4),
            )
        )
    return out
