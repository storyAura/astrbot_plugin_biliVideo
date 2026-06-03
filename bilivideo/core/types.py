"""Common dataclasses used across the plugin.

These mirror the dicts the previous version returned from API helpers.
Switching to dataclasses gives us autocomplete in IDEs, eliminates
typo-prone string indexing, and makes serialization explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class VideoInfo:
    """View / details for a single Bilibili video."""

    bvid: str
    title: str
    pic: str = ""
    desc: str = ""
    pubdate: int = 0
    duration: int = 0
    owner_name: str = "未知"
    owner_mid: str = ""
    view: int = 0
    danmaku: int = 0
    like: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_pic(self) -> str:
        if self.pic.startswith("//"):
            return "https:" + self.pic
        return self.pic

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}"


@dataclass(slots=True, frozen=True)
class UploaderInfo:
    """UP 主基本资料。"""

    mid: str
    name: str
    face: str = ""
    sign: str = ""


@dataclass(slots=True, frozen=True)
class SearchVideoItem:
    """搜索结果中的单个视频条目。"""

    bvid: str
    aid: int
    title: str
    author: str
    mid: int
    pic: str
    description: str
    play: int
    danmaku: int
    like: int
    favorites: int
    duration: str
    pubdate: int
    tag: str

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}"


@dataclass(slots=True, frozen=True)
class SearchResult:
    results: tuple[SearchVideoItem, ...]
    num_results: int
    page: int
    num_pages: int


@dataclass(slots=True, frozen=True)
class LatestVideo:
    """UP 主投稿列表中的简要视频信息。"""

    bvid: str
    title: str
    pic: str = ""
    pubdate: int = 0
    duration: str = ""
    description: str = ""


@dataclass(slots=True, frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(slots=True, frozen=True)
class TranscriptResult:
    language: str | None
    full_text: str
    segments: tuple[TranscriptSegment, ...]
    raw: dict[str, Any] | None = None

    @property
    def has_content(self) -> bool:
        return bool(self.segments)


@dataclass(slots=True, frozen=True)
class AudioDownloadResult:
    file_path: str
    title: str
    duration: float
    cover_url: str | None
    platform: str
    video_id: str
    raw_info: dict[str, Any] = field(default_factory=dict)
