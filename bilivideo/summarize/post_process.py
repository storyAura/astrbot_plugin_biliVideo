"""Post-processing helpers for LLM-generated Markdown."""

from __future__ import annotations

import re

from ..core.constants import TIMESTAMP_REGEX


def replace_timestamp_markers(markdown: str) -> str:
    """Convert LLM `Content-[time]` placeholders to font-safe tags."""

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1) or match.group(2)
        parts = [int(part) for part in token.split(":")]
        if parts[-1] >= 60 or (len(parts) == 3 and parts[-2] >= 60):
            return match.group(0)
        if len(parts) == 3:
            normalized = f"{parts[0]}:{parts[1]:02d}:{parts[2]:02d}"
        else:
            normalized = f"{parts[0]:02d}:{parts[1]:02d}"
        return f"[{normalized}]"

    return TIMESTAMP_REGEX.sub(_sub, markdown)


def smart_truncate(markdown: str, max_length: int) -> str:
    """Truncate at a paragraph boundary while keeping at least 70% content.

    Returns the original string when no truncation is needed.
    """

    if len(markdown) <= max_length:
        return markdown
    truncated = markdown[:max_length]
    min_keep = int(max_length * 0.7)
    last_break = truncated.rfind("\n\n")
    if last_break > min_keep:
        truncated = truncated[:last_break]
    return (
        truncated
        + "\n\n---"
        + "\n\n⚠️ **内容过长提示**"
        + f"\n\n本视频内容非常丰富(超过 {max_length} 字符限制),"
        + "\n以上为核心内容摘要。"
        + "\n\n💡 如需完整总结,可在配置中调整 `max_note_length` 参数。"
    )
