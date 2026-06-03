"""Trigger keyword set used by the auto-detect handler.

Wraps a frozenset for fast membership checks plus a substring-match helper
that is tolerant of mixed-case input. The list is built from the
configuration so users can customize it without editing source.
"""

from __future__ import annotations

from collections.abc import Iterable

DEFAULT_TRIGGER_KEYWORDS: tuple[str, ...] = (
    "总结", "看看", "看一下", "看下", "分析",
    "讲的啥", "讲什么", "说的啥", "说什么",
    "内容", "视频", "这个", "这视频",
    "帮我看", "帮忙看", "解析", "翻译",
    "summary", "summarize", "analyze",
    "video", "watch", "check", "see",
)

# Keywords that count as "this message references Bilibili itself"
BILIBILI_HINTS: tuple[str, ...] = (
    "bilibili", "b23.tv", "bv", "www.bilibili.com", "哔哩哔哩",
)


class TriggerSet:
    """Case-insensitive substring matcher."""

    __slots__ = ("_keywords",)

    def __init__(self, keywords: Iterable[str]) -> None:
        cleaned = tuple(k.strip().lower() for k in keywords if k and k.strip())
        self._keywords = cleaned or tuple(k.lower() for k in DEFAULT_TRIGGER_KEYWORDS)

    @property
    def keywords(self) -> tuple[str, ...]:
        return self._keywords

    def matches(self, text: str) -> bool:
        if not text:
            return False
        lower = text.lower()
        return any(kw in lower for kw in self._keywords)

    @staticmethod
    def has_bilibili_hint(text: str) -> bool:
        if not text:
            return False
        lower = text.lower()
        return any(hint in lower for hint in BILIBILI_HINTS)
