"""Helpers for splitting long Markdown into chat-friendly chunks."""

from __future__ import annotations


def split_text_for_messages(text: str, *, max_chunk: int = 2000) -> list[str]:
    """Split `text` so each chunk stays under `max_chunk` characters.

    Tries paragraph boundaries first, then line boundaries, then a hard cut.
    """

    if len(text) <= max_chunk:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chunk:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, max_chunk)
        if cut <= 0 or cut < int(max_chunk * 0.5):
            cut = remaining.rfind("\n", 0, max_chunk)
        if cut <= 0 or cut < int(max_chunk * 0.3):
            cut = max_chunk
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks


def format_count(value: int) -> str:
    """Pretty-print large integers with `亿/万` suffixes."""

    if value >= 100_000_000:
        return f"{value / 100_000_000:.1f}亿"
    if value >= 10_000:
        return f"{value / 10_000:.1f}万"
    return str(value)
