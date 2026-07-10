"""Bridge between the renderer and the AstrBot message components.

`render_note_components()` returns either a list of `Image` components
(image mode) or a plain string (text mode), so handlers can decide how to
package the result without knowing about the renderer internals.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

from ..core.exceptions import PartialRenderError, RenderError
from ..core.logging import get_logger
from ..services import BiliVideoServices

logger = get_logger("BiliVideo/RenderHelper")

try:
    from astrbot.api.message_components import Image, Plain  # type: ignore[import]
except Exception:  # pragma: no cover - test stub
    Image = None  # type: ignore[assignment]
    Plain = None  # type: ignore[assignment]


async def render_note_components(
    services: BiliVideoServices, markdown_text: str
) -> list[Any] | str:
    """Convert Markdown to image components or raw text — never raises.

    Rendering (wkhtmltoimage subprocess or Pillow CPU drawing) takes seconds,
    so it runs in a worker thread to keep the event loop responsive.

    Any unexpected failure (a renderer surprise, a filesystem error while
    validating an output path, an AstrBot component constructor blowing up,
    …) degrades to a visible text fallback. A rendering bug can therefore
    never crash the calling handler or leave the user with no response.
    """

    try:
        return await asyncio.to_thread(
            _render_note_components_inner, services, markdown_text
        )
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.warning(
            f"render_note_components unexpected failure: {exc}", exc_info=True
        )
        return _render_fallback_text(markdown_text, f"渲染流程异常: {exc}")


def _render_note_components_inner(
    services: BiliVideoServices, markdown_text: str
) -> list[Any] | str:
    if not services.config.output_image:
        return markdown_text
    if Image is None:
        return _render_fallback_text(markdown_text, "AstrBot Image 组件不可用")

    base_filename = f"note_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    try:
        paths = services.renderer.render(
            markdown_text,
            base_filename=base_filename,
            max_cards_per_image=services.config.max_cards_per_image,
            enable_split=services.config.enable_auto_split,
        )
        partial_failed_pages: list[int] = []
        partial_page_errors: dict[int, str] = {}
    except PartialRenderError as exc:
        logger.warning(f"partial render fallback text appended: {exc}")
        paths = exc.generated_paths
        partial_failed_pages = exc.failed_pages
        partial_page_errors = exc.page_errors
    except RenderError as exc:
        logger.warning(f"render fallback to text: {exc}")
        return _render_fallback_text(markdown_text, str(exc))

    components: list[Any] = []
    fallback_texts: list[str] = []
    invalid_paths: list[str] = []
    for path in paths:
        if not isinstance(path, Path):
            path = Path(path)
        try:
            usable = path.exists() and path.stat().st_size > 0
        except OSError:
            usable = False
        if not usable:
            invalid_paths.append(str(path))
            continue
        try:
            components.append(Image.fromFileSystem(str(path)))
        except Exception as exc:
            logger.warning(f"image component build failed for {path}: {exc}")
            fallback_texts.append(f"⚠️ 图片文件 {path.name} 发送失败,以下为文本兜底:\n\n{markdown_text}")
    if partial_failed_pages:
        error_details = "; ".join(
            f"第 {page} 页: {partial_page_errors.get(page, '未知原因')}"
            for page in partial_failed_pages
        )
        fallback_texts.append(
            f"⚠️ 第 {', '.join(str(p) for p in partial_failed_pages)} 页图片生成失败,"
            f"原因: {error_details}\n以下为完整文本兜底:\n\n" + markdown_text
        )
    if invalid_paths:
        logger.warning(f"renderer returned invalid image paths: {invalid_paths}")
        fallback_texts.append(f"图片路径无效: {', '.join(invalid_paths)}")
    if not components:
        reason = "\n".join(fallback_texts) if fallback_texts else "图片组件生成失败"
        return _render_fallback_text(markdown_text, reason)
    if fallback_texts:
        fallback_text = "\n\n".join(fallback_texts)
        if Plain is None:
            logger.warning("Plain component unavailable; cannot append render fallback text")
            return components
        components.append(Plain(fallback_text))
    return components


def _render_fallback_text(markdown_text: str, reason: str) -> str:
    clean_reason = (reason or "未知原因").strip()
    return f"⚠️ 图片渲染失败,已退回纯文本\n原因: {clean_reason}\n\n{markdown_text}"
