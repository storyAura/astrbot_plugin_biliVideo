"""Structured summary schema and prompt contract tests."""

from __future__ import annotations

import pytest

from bilivideo.core.types import TranscriptSegment
from bilivideo.llm.prompts import build_prompt
from bilivideo.llm.structured_summary import (
    StructuredSummaryError,
    parse_structured_summary,
    structured_summary_to_markdown,
    summary_tool_parameters,
)


def _payload() -> dict[str, object]:
    return {
        "title": "# 测试视频 - UP",
        "chapters": [
            {
                "title": "## 开场",
                "timestamp_seconds": 0,
                "body_markdown": "- 结论为 $x^2$。",
            },
            {
                "title": "长视频章节",
                "timestamp_seconds": 3723,
                "body_markdown": "保留公式 $\\frac{1}{2}$。",
            },
        ],
        "ai_summary": "完整总结。",
    }


def test_valid_payload_is_normalized_to_renderer_safe_markdown() -> None:
    summary = parse_structured_summary(
        _payload(), max_timestamp_seconds=4000, require_ai_summary=True
    )

    markdown = structured_summary_to_markdown(summary)

    assert markdown.startswith("# 测试视频 - UP")
    assert "## 开场 [00:00]" in markdown
    assert "## 长视频章节 [1:02:03]" in markdown
    assert "$\\frac{1}{2}$" in markdown
    assert "⏱" not in markdown
    assert markdown.endswith("## AI 总结\n完整总结。")


@pytest.mark.parametrize(
    ("timestamp", "max_timestamp", "message"),
    [
        (11, 10, "outside video range"),
        (-1, 10, "outside video range"),
        (True, 10, "must be an integer"),
    ],
)
def test_rejects_invalid_timestamps(timestamp: object, max_timestamp: int, message: str) -> None:
    payload = _payload()
    payload["chapters"] = [
        {"title": "章节", "timestamp_seconds": timestamp, "body_markdown": "内容"}
    ]

    with pytest.raises(StructuredSummaryError, match=message):
        parse_structured_summary(
            payload, max_timestamp_seconds=max_timestamp, require_ai_summary=True
        )


def test_rejects_decreasing_timestamps() -> None:
    payload = _payload()
    chapters = payload["chapters"]
    assert isinstance(chapters, list)
    assert isinstance(chapters[0], dict)
    assert isinstance(chapters[1], dict)
    chapters[0]["timestamp_seconds"] = 20
    chapters[1]["timestamp_seconds"] = 10

    with pytest.raises(StructuredSummaryError, match="monotonic"):
        parse_structured_summary(payload, max_timestamp_seconds=30, require_ai_summary=True)


def test_rejects_nested_primary_headings() -> None:
    payload = _payload()
    chapters = payload["chapters"]
    assert isinstance(chapters, list)
    assert isinstance(chapters[0], dict)
    chapters[0]["body_markdown"] = "## 不应出现的标题"

    with pytest.raises(StructuredSummaryError, match="contains h1/h2"):
        parse_structured_summary(payload, max_timestamp_seconds=4000, require_ai_summary=True)


def test_schema_only_requires_ai_summary_when_enabled() -> None:
    enabled = summary_tool_parameters(include_ai_summary=True)
    disabled = summary_tool_parameters(include_ai_summary=False)

    assert "ai_summary" in enabled["required"]
    assert "ai_summary" not in disabled["required"]
    assert "ai_summary" not in disabled["properties"]


def test_structured_prompt_uses_integer_seconds_without_markdown_conflict() -> None:
    segments = (TranscriptSegment(start=5, end=10, text="内容"),)

    structured = build_prompt(
        title="标题",
        segments=segments,
        enable_link=True,
        structured_output=True,
    )
    legacy = build_prompt(
        title="标题",
        segments=segments,
        enable_link=True,
        structured_output=False,
    )

    assert "submit_video_summary" in structured
    assert "00:05 | 5s - 内容" in structured
    assert "第一行必须是 h1" not in structured
    assert "Content-[mm:ss]" not in structured
    assert "submit_video_summary" not in legacy
    assert "00:05 - 内容" in legacy
    assert "Content-[mm:ss]" in legacy
