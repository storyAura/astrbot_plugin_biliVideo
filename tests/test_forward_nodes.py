"""Forward-message node builders, exercised with stubbed AstrBot components."""

from __future__ import annotations

import pytest

from bilivideo.core.types import VideoInfo
from bilivideo.messaging import forward


class _Plain:
    def __init__(self, text: str) -> None:
        self.text = text


class _Image:
    def __init__(self, url: str) -> None:
        self.url = url

    @classmethod
    def fromURL(cls, url: str) -> _Image:  # noqa: N802 - mirrors AstrBot's API
        return cls(url)


class _Node:
    def __init__(self, content: list, name: str, uin: str) -> None:
        self.content = content
        self.name = name
        self.uin = uin


class _Nodes:
    def __init__(self, nodes: list) -> None:
        self.nodes = nodes


@pytest.fixture
def stub_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(forward, "Plain", _Plain)
    monkeypatch.setattr(forward, "Image", _Image)
    monkeypatch.setattr(forward, "Node", _Node)
    monkeypatch.setattr(forward, "Nodes", _Nodes)


def _info(bvid: str = "BV1test", title: str = "标题") -> VideoInfo:
    return VideoInfo(bvid=bvid, title=title, pic="https://img/x.jpg", owner_name="UP")


def test_raises_without_astrbot() -> None:
    with pytest.raises(RuntimeError):
        forward.build_video_forward_nodes(_info(), "text", bot_name="b", bot_uin="0")
    with pytest.raises(RuntimeError):
        forward.build_multi_video_forward_nodes(
            [_info()], "text", bot_name="b", bot_uin="0", header="h"
        )


def test_single_video_with_header(stub_components: None) -> None:
    result = forward.build_video_forward_nodes(
        _info(), "总结内容", bot_name="bot", bot_uin="0", header="🔔 新视频!"
    )
    texts = [c.text for node in result.nodes for c in node.content if isinstance(c, _Plain)]
    assert texts[0] == "🔔 新视频!"
    assert any("📺 标题" in t for t in texts)
    assert any(t.startswith("📝 AI 视频总结") for t in texts)


def test_single_video_without_header_starts_with_cover(stub_components: None) -> None:
    result = forward.build_video_forward_nodes(_info(), "总结", bot_name="b", bot_uin="0")
    assert isinstance(result.nodes[0].content[0], _Image)


def test_multi_video_layout_and_labels(stub_components: None) -> None:
    infos = [_info("BV1", "甲"), _info("BV2", "乙")]
    rendered = [_Image("https://img/p1.png"), _Image("https://img/p2.png")]
    result = forward.build_multi_video_forward_nodes(
        infos, rendered, bot_name="b", bot_uin="0", header="📝 搜索结果总结(共 2 个视频)"
    )
    # header + 2 videos + 2 summary pages
    assert len(result.nodes) == 5
    assert result.nodes[0].content[0].text == "📝 搜索结果总结(共 2 个视频)"
    assert "📺 视频 1: 甲" in result.nodes[1].content[-1].text
    assert "📺 视频 2: 乙" in result.nodes[2].content[-1].text
    labels = [node.content[0].text for node in result.nodes[3:]]
    assert labels == ["📝 AI 综合总结", "📝 AI 综合总结(第 2 页)"]


def test_multi_video_string_summary_is_chunked_with_label(stub_components: None) -> None:
    result = forward.build_multi_video_forward_nodes(
        [_info()], "综合总结文本", bot_name="b", bot_uin="0", header="头"
    )
    summary = result.nodes[-1].content[0].text
    assert summary.startswith("📝 AI 综合总结\n\n综合总结文本")
