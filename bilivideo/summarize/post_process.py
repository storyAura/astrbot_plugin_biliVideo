"""Post-processing helpers for LLM-generated Markdown."""

from __future__ import annotations

from ..core.constants import TIMESTAMP_REGEX


def replace_timestamp_markers(markdown: str) -> str:
    """Convert `Content-04:16` / `Content-[04:16]` placeholders to ⏱ tags."""

    def _sub(match: object) -> str:
        mm = match.group(1) or match.group(3)
        ss = match.group(2) or match.group(4)
        return f"⏱ {mm}:{ss}"

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
