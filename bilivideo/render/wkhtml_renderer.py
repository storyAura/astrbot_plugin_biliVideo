"""Markdown → PNG renderer backed by `imgkit` + wkhtmltopdf."""

from __future__ import annotations

import base64
import html
import io
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _math_image_element(formula: str, *, display: bool, max_width: int) -> Any:
    """Render one formula into a self-contained image element for wkhtml."""

    from xml.etree import ElementTree

    from .pillow_renderer import _render_math_image

    font_size = 18 if display else 14
    color = (226, 232, 240) if display else (201, 206, 220)
    image = _render_math_image(
        formula,
        font_size=font_size,
        color=color,
        max_width=max_width,
    )
    baseline_ascent = int(image.info.get("baseline_ascent", image.height))
    baseline_descent = max(0, image.height - baseline_ascent)
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")

    class_name = "math-display" if display else "math-inline"
    element = ElementTree.Element(
        "img",
        {
            "class": class_name,
            "src": f"data:image/png;base64,{base64.b64encode(image_bytes.getvalue()).decode()}",
            "alt": formula,
            "width": str(image.width),
            "height": str(image.height),
        },
    )
    if not display:
        element.set("style", f"vertical-align:-{baseline_descent}px")
    return element


def _markdown_to_html(markdown_text: str, *, max_math_width: int) -> str:
    """Convert Markdown to HTML and pre-render TeX math without JavaScript."""

    from xml.etree import ElementTree

    import markdown as md
    from markdown.extensions import Extension
    from markdown.inlinepatterns import InlineProcessor
    from markdown.preprocessors import Preprocessor
    from markdown.util import AtomicString

    class MathInlineProcessor(InlineProcessor):
        def __init__(self, pattern: str, *, display: bool = False) -> None:
            super().__init__(pattern)
            self._display = display

        def handleMatch(self, match, data):  # noqa: N802
            formula = match.group(1).strip()
            try:
                element = _math_image_element(
                    formula,
                    display=self._display,
                    max_width=max_math_width,
                )
            except Exception as exc:
                logger.warning(f"wkhtml inline formula render failed; using source: {exc}")
                element = ElementTree.Element("span", {"class": "math-source"})
                element.text = AtomicString(match.group(0))
            return element, match.start(0), match.end(0)

    class MathBlockPreprocessor(Preprocessor):
        _single_line_patterns = (
            (r"^\\\[(.+)\\\]$", r"\[", r"\]"),
            (r"^\$\$(.+)\$\$$", "$$", "$$"),
        )

        @staticmethod
        def _render_block(formula: str, source: str) -> str:
            try:
                image = _math_image_element(
                    formula.strip(),
                    display=True,
                    max_width=max_math_width,
                )
            except Exception as exc:
                logger.warning(f"wkhtml display formula render failed; using source: {exc}")
                return f'<div class="math-source math-source-block">{html.escape(source)}</div>'
            image_html = ElementTree.tostring(image, encoding="unicode", method="html")
            return f'<div class="math-block">{image_html}</div>'

        def run(self, lines: list[str]) -> list[str]:
            output: list[str] = []
            index = 0
            while index < len(lines):
                stripped = lines[index].strip()

                single_line = None
                for pattern, opener, closer in self._single_line_patterns:
                    match = re.match(pattern, stripped)
                    if match:
                        single_line = (match.group(1), f"{opener}{match.group(1)}{closer}")
                        break
                if single_line is not None:
                    formula, source = single_line
                    output.extend(("", self._render_block(formula, source), ""))
                    index += 1
                    continue

                if stripped not in {r"\[", "$$"}:
                    output.append(lines[index])
                    index += 1
                    continue

                closer = r"\]" if stripped == r"\[" else "$$"
                end = index + 1
                while end < len(lines) and lines[end].strip() != closer:
                    end += 1
                if end >= len(lines):
                    output.append(lines[index])
                    index += 1
                    continue

                formula_lines = lines[index + 1 : end]
                source_lines = lines[index : end + 1]
                output.extend(
                    (
                        "",
                        self._render_block("\n".join(formula_lines), "\n".join(source_lines)),
                        "",
                    )
                )
                index = end + 1
            return output

    class MathImageExtension(Extension):
        def extendMarkdown(self, markdown) -> None:  # noqa: N802
            # Fenced code is stashed at priority 25; emit block HTML before
            # the core html_block preprocessor stashes it at priority 20.
            markdown.preprocessors.register(MathBlockPreprocessor(markdown), "math_block_image", 21)
            # Backtick code runs at 190 and escaped delimiters at 180.
            markdown.inlinePatterns.register(
                MathInlineProcessor(r"(?<!\\)\\\((.+?)(?<!\\)\\\)"),
                "math_bracket_inline_image",
                185,
            )
            markdown.inlinePatterns.register(
                MathInlineProcessor(r"(?<!\\)(?<!\$)\$(?!\$)(.+?)(?<!\\)\$(?!\$)"),
                "math_dollar_inline_image",
                184,
            )

    return md.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "nl2br", MathImageExtension()],
    )


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
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise RenderError(f"missing dependency: {exc}") from exc

        try:
            html_body = _markdown_to_html(
                markdown_text,
                max_math_width=max(160, self._image_width - 120),
            )
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise RenderError(f"missing dependency: {exc}") from exc
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
