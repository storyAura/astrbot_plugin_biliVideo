"""Markdown → PNG renderer backed by `imgkit` + wkhtmltopdf."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from ..core.exceptions import PartialRenderError, RenderError
from ..core.logging import get_logger
from .pagination import split_by_chapters
from .templates import (
    build_full_html,
    extract_title,
    highlight_timestamps,
    sanitize_html,
    wrap_chapters_in_cards,
)

logger = get_logger("BiliVideo/Render")


class WkHtmlRenderer:
    """Renders Markdown into one or more PNG files."""

    def __init__(self, *, output_dir: str | Path, image_width: int = 900) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._image_width = image_width

    def render(
        self,
        markdown_text: str,
        *,
        base_filename: str,
        max_cards_per_image: int = 6,
        enable_split: bool = True,
    ) -> list[Path]:
        chapter_count = sum(1 for line in markdown_text.splitlines() if line.startswith("## "))
        if not enable_split or chapter_count <= max_cards_per_image:
            return self._render_single(markdown_text, base_filename)

        pages = split_by_chapters(markdown_text, max_cards=max_cards_per_image)
        if len(pages) == 1:
            return self._render_single(pages[0], base_filename)

        outputs: list[Path] = []
        failed_pages: list[int] = []
        page_errors: dict[int, str] = {}
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = len(pages)
        for idx, page_md in enumerate(pages, start=1):
            destination = self._output_dir / f"{base_filename}_p{idx}.png"
            footer_time = f"{now_str} | 第 {idx}/{total} 页"
            try:
                self._render_html_to_png(
                    page_md,
                    destination,
                    footer_time=footer_time,
                    page_label=None if total == 1 else f"(第 {idx}/{total} 页)",
                )
            except RenderError as exc:
                logger.warning(
                    f"page {idx}/{total} failed: {exc}; "
                    f"page_chars={len(page_md)} chapters={page_md.count(chr(10) + '## ')}"
                )
                failed_pages.append(idx)
                page_errors[idx] = str(exc)
                continue
            outputs.append(destination)
        if failed_pages and outputs:
            raise PartialRenderError(
                f"partial render failed; failed_pages={failed_pages}, "
                f"succeeded_pages={[p.name for p in outputs]}",
                generated_paths=outputs,
                failed_pages=failed_pages,
                page_errors=page_errors,
            )
        if not outputs:
            raise RenderError("all pages failed to render")
        return outputs

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _render_single(self, markdown_text: str, base_filename: str) -> list[Path]:
        destination = self._output_dir / f"{base_filename}.png"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._render_html_to_png(markdown_text, destination, footer_time=now_str)
        return [destination]

    def _render_html_to_png(
        self,
        markdown_text: str,
        destination: Path,
        *,
        footer_time: str,
        page_label: str | None = None,
    ) -> None:
        try:
            import imgkit
            import markdown as md
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise RenderError(f"missing dependency: {exc}") from exc

        html_body = md.markdown(
            markdown_text,
            extensions=["tables", "fenced_code", "nl2br"],
        )
        html_body = sanitize_html(html_body)
        html_body = highlight_timestamps(html_body)
        title_text, html_body = extract_title(html_body)
        if page_label:
            title_text = f"{title_text} {page_label}"
        html_body = wrap_chapters_in_cards(html_body)

        full_html = build_full_html(
            html_body,
            title_text=title_text,
            footer_time=footer_time,
            width=self._image_width,
        )

        options = {
            "format": "png",
            "width": str(self._image_width),
            "encoding": "UTF-8",
            "quality": "94",
            "disable-javascript": "",
            "disable-local-file-access": "",
            "no-stop-slow-scripts": "",
            "disable-smart-width": "",
        }

        destination.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        try:
            imgkit.from_string(full_html, str(destination), options=options)
        except Exception as exc:
            raise RenderError(f"imgkit failure: {exc}") from exc
        elapsed = round(time.monotonic() - started, 2)

        if not destination.exists():
            raise RenderError("imgkit produced no file")
        size = destination.stat().st_size
        if size < 2048:
            # A real chat-card PNG is always several KB; a sub-2KB file
            # means a blank or clipped render; fail rather than delivering it.
            raise RenderError(
                f"imgkit produced an implausibly small file ({size}B): {destination}"
            )
        logger.info(f"rendered {destination.name} ({size} bytes, {elapsed}s)")
