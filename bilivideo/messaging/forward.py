"""Single source of truth for building forward-message Nodes.

The previous implementation duplicated this logic in four places; here we
expose a single function that the handler layer invokes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..core.types import VideoInfo
from .builders import format_video_info_block
from .chunker import split_text_for_messages

# Lazy AstrBot imports so the module is import-safe in tests.
try:
    from astrbot.api.message_components import Image, Node, Nodes, Plain  # type: ignore[import]
except Exception:  # pragma: no cover - test env stubs
    Plain = Image = Node = Nodes = None  # type: ignore[assignment]


def build_video_forward_nodes(
    info: VideoInfo,
    rendered: Sequence[Any] | str,
    *,
    bot_name: str,
    bot_uin: str,
    summary_label: str = "📝 AI 视频总结",
) -> Any:
    """Pack `[cover+title, info, summary]` into a `Nodes` payload.

    `rendered` may be a sequence of `Image` components (image mode) or a raw
    Markdown string (text mode); both are split sensibly so platforms with
    a 2000-char per-message ceiling don't truncate.
    """

    if Node is None:  # tests / imports without AstrBot installed
        raise RuntimeError("AstrBot message components are unavailable")

    nodes: list[Any] = []

    # 1. cover + title
    cover_content: list[Any] = []
    if info.normalized_pic:
        cover_content.append(Image.fromURL(info.normalized_pic))
    cover_content.append(Plain(f"📺 {info.title}"))
    nodes.append(Node(content=cover_content, name=bot_name, uin=bot_uin))

    # 2. metadata
    nodes.append(
        Node(
            content=[Plain(format_video_info_block(info))],
            name=bot_name,
            uin=bot_uin,
        )
    )

    # 3. summary content
    if isinstance(rendered, str):
        for idx, chunk in enumerate(split_text_for_messages(rendered)):
            label = summary_label if idx == 0 else f"{summary_label}(第 {idx + 1} 部分)"
            nodes.append(Node(content=[Plain(f"{label}\n\n{chunk}")], name=bot_name, uin=bot_uin))
    else:
        image_idx = 0
        for comp in rendered:
            if Plain is not None and isinstance(comp, Plain):
                label = "⚠️ 渲染失败说明 / 文本兜底"
            else:
                image_idx += 1
                label = summary_label if image_idx == 1 else f"{summary_label}(第 {image_idx} 页)"
            nodes.append(Node(content=[Plain(label), comp], name=bot_name, uin=bot_uin))

    return Nodes(nodes=nodes)
