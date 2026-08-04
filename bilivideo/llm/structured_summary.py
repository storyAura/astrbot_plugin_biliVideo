"""Structured video-summary schema used by AstrBot function calling."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SUMMARY_TOOL_NAME = "submit_video_summary"
SUMMARY_FORMAT_VERSION = "structured-v1"


@dataclass(slots=True, frozen=True)
class StructuredSummaryAttempt:
    """Raw result of an optional structured-output request."""

    arguments: object | None = None
    fallback_text: str = ""


@dataclass(slots=True, frozen=True)
class SummaryChapter:
    title: str
    timestamp_seconds: int
    body_markdown: str


@dataclass(slots=True, frozen=True)
class StructuredSummary:
    title: str
    chapters: tuple[SummaryChapter, ...]
    ai_summary: str = ""


class StructuredSummaryError(ValueError):
    """Tool arguments do not satisfy the summary contract."""


def summary_tool_parameters(*, include_ai_summary: bool) -> dict[str, Any]:
    """Return the JSON Schema sent to AstrBot's single output tool."""

    properties: dict[str, Any] = {
        "title": {
            "type": "string",
            "description": "视频标题和作者，不要包含 Markdown 标题符号。",
        },
        "chapters": {
            "type": "array",
            "minItems": 1,
            "description": "按照视频时间顺序排列的主要章节。",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "章节标题，不要包含 ## 前缀。",
                    },
                    "timestamp_seconds": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "章节开始时间，必须复制转录片段中的整数秒。",
                    },
                    "body_markdown": {
                        "type": "string",
                        "description": (
                            "章节内容，可使用列表、引用、表格、加粗和 LaTeX，"
                            "但不要再生成一级或二级标题。"
                        ),
                    },
                },
                "required": ["title", "timestamp_seconds", "body_markdown"],
            },
        },
    }
    required = ["title", "chapters"]
    if include_ai_summary:
        properties["ai_summary"] = {
            "type": "string",
            "description": "对整个视频的专业中文总结，不要包含标题。",
        }
        required.append("ai_summary")

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def parse_structured_summary(
    arguments: object,
    *,
    max_timestamp_seconds: int,
    require_ai_summary: bool,
) -> StructuredSummary:
    """Validate and normalize one tool-call payload."""

    if not isinstance(arguments, dict):
        raise StructuredSummaryError("tool arguments must be an object")

    title = _heading(arguments.get("title"), "title")
    raw_chapters = arguments.get("chapters")
    if not isinstance(raw_chapters, list) or not raw_chapters:
        raise StructuredSummaryError("chapters must be a non-empty array")
    if len(raw_chapters) > 32:
        raise StructuredSummaryError("chapters exceeds the 32-item limit")

    chapters: list[SummaryChapter] = []
    previous_timestamp = -1
    for index, raw_chapter in enumerate(raw_chapters):
        if not isinstance(raw_chapter, dict):
            raise StructuredSummaryError(f"chapter {index + 1} must be an object")
        chapter_title = _heading(raw_chapter.get("title"), f"chapter {index + 1} title")
        timestamp = raw_chapter.get("timestamp_seconds")
        if isinstance(timestamp, bool) or not isinstance(timestamp, int):
            raise StructuredSummaryError(f"chapter {index + 1} timestamp must be an integer")
        if timestamp < 0 or timestamp > max_timestamp_seconds:
            raise StructuredSummaryError(
                f"chapter {index + 1} timestamp {timestamp}s is outside video range"
            )
        if timestamp < previous_timestamp:
            raise StructuredSummaryError("chapter timestamps must be monotonic")

        body = raw_chapter.get("body_markdown")
        if not isinstance(body, str) or not body.strip():
            raise StructuredSummaryError(f"chapter {index + 1} body_markdown is empty")
        body = body.strip()
        if re.search(r"(?m)^ {0,3}#{1,2}\s+", body):
            raise StructuredSummaryError(f"chapter {index + 1} body contains h1/h2 headings")

        chapters.append(SummaryChapter(chapter_title, timestamp, body))
        previous_timestamp = timestamp

    raw_ai_summary = arguments.get("ai_summary", "")
    if not isinstance(raw_ai_summary, str):
        raise StructuredSummaryError("ai_summary must be a string")
    ai_summary = raw_ai_summary.strip()
    if require_ai_summary and not ai_summary:
        raise StructuredSummaryError("ai_summary is required")

    return StructuredSummary(title, tuple(chapters), ai_summary)


def structured_summary_to_markdown(summary: StructuredSummary) -> str:
    """Build renderer-safe Markdown with timestamps fixed on h2 lines."""

    pieces = [f"# {summary.title}"]
    for chapter in summary.chapters:
        timestamp = _format_seconds(chapter.timestamp_seconds)
        pieces.append(f"## {chapter.title} [{timestamp}]\n{chapter.body_markdown}")
    if summary.ai_summary:
        pieces.append(f"## AI 总结\n{summary.ai_summary}")
    return "\n\n".join(pieces).strip()


def _heading(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise StructuredSummaryError(f"{label} must be a string")
    cleaned = re.sub(r"^\s*#{1,6}\s*", "", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise StructuredSummaryError(f"{label} is empty")
    return cleaned


def _format_seconds(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
