"""Markdown and math renderer implemented entirely with Python packages.

``markdown-it-py`` produces a real Markdown syntax tree, Matplotlib MathText
turns common TeX expressions into transparent bitmaps, and Pillow composes the
final chat-friendly cards. No browser, JavaScript runtime, or system TeX
installation is required.
"""

from __future__ import annotations

import functools
import math
import os
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..core.exceptions import PartialRenderError, RenderError
from ..core.logging import get_logger
from .pagination import split_by_chapters
from .theme import card_color_for

if TYPE_CHECKING:  # pragma: no cover
    from PIL.Image import Image as PILImage
    from PIL.ImageFont import FreeTypeFont

logger = get_logger("BiliVideo/PythonRender")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED_CJK_FONT = str(_REPO_ROOT / "fonts" / "NotoSansSC-Regular.subset.otf")
_BUNDLED_MONO_FONT = str(_REPO_ROOT / "fonts" / "JetBrainsMono-Light.ttf")

_CJK_FONT_CANDIDATES: tuple[str, ...] = (
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/mnt/c/Windows/Fonts/msyh.ttc",
    "/mnt/c/Windows/Fonts/simhei.ttf",
    "/mnt/c/Windows/Fonts/simsun.ttc",
    _BUNDLED_CJK_FONT,
)
_FALLBACK_FONT_CANDIDATES: tuple[str, ...] = (
    _BUNDLED_MONO_FONT,
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/mnt/c/Windows/Fonts/arial.ttf",
)


@functools.lru_cache(maxsize=1)
def _find_cjk_font() -> str | None:
    return next((path for path in _CJK_FONT_CANDIDATES if os.path.exists(path)), None)


@functools.lru_cache(maxsize=1)
def _find_fallback_font() -> str | None:
    return next((path for path in _FALLBACK_FONT_CANDIDATES if os.path.exists(path)), None)


def check_pillow_ready() -> tuple[bool, str]:
    """Check every dependency needed by the Python renderer."""

    try:
        from markdown_it import MarkdownIt  # noqa: F401
        from matplotlib.mathtext import MathTextParser  # noqa: F401
        from mdit_py_plugins.dollarmath import dollarmath_plugin  # noqa: F401
        from mdit_py_plugins.texmath import texmath_plugin  # noqa: F401
        from PIL import ImageFont
    except ImportError as exc:
        return False, f"missing Python dependency: {exc}"

    font_path = _find_cjk_font()
    if font_path is not None:
        try:
            ImageFont.truetype(font_path, 14)
        except Exception as exc:
            return False, f"CJK font cannot be loaded: {font_path} ({exc})"
        return True, f"Markdown+MathText; font={font_path}"

    fallback_path = _find_fallback_font()
    if fallback_path is None:
        return True, "Markdown+MathText; Pillow default font; no CJK font discovered"
    try:
        ImageFont.truetype(fallback_path, 14)
    except Exception as exc:
        return False, f"fallback font cannot be loaded: {fallback_path} ({exc})"
    return True, f"Markdown+MathText; fallback_font={fallback_path}; no CJK font discovered"


_FONT_CACHE = threading.local()


def _load_font(size: int, *, mono: bool = False):
    from PIL import ImageFont

    if mono and os.path.exists(_BUNDLED_MONO_FONT):
        font_path = _BUNDLED_MONO_FONT
    else:
        font_path = _find_cjk_font() or _find_fallback_font()

    if font_path is not None:
        cache: dict = getattr(_FONT_CACHE, "fonts", None)
        if cache is None:
            cache = {}
            _FONT_CACHE.fonts = cache
        cached = cache.get((font_path, size))
        if cached is not None:
            return cached, font_path
        try:
            font = ImageFont.truetype(font_path, size)
        except Exception as exc:
            logger.warning(f"font load failed ({font_path}): {exc}; using Pillow default")
        else:
            cache[(font_path, size)] = font
            return font, font_path
    return ImageFont.load_default(), "Pillow default"


_UNSUPPORTED_GLYPHS_RE = re.compile(
    "["
    "\U0001f000-\U0001ffff"
    "\U00002600-\U000027bf"
    "\U00002b00-\U00002bff"
    "\U00002300-\U000023ff"
    "\U0000fe00-\U0000fe0f"
    "‍"
    "]"
)


def _strip_unsupported_glyphs(text: str) -> str:
    if not text:
        return text
    cleaned = _UNSUPPORTED_GLYPHS_RE.sub("", text)
    if cleaned == text:
        return text
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


_TS_RE = re.compile(r"^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*")


def _line_advance(font: object) -> int:
    size = int(getattr(font, "size", 16))
    return max(size + 6, round(size * 1.55))


@dataclass(slots=True, frozen=True)
class _InlineSpan:
    text: str
    kind: str = "text"  # text | code | math | link | timestamp
    bold: bool = False
    italic: bool = False


@dataclass(slots=True, frozen=True)
class _TableCell:
    spans: tuple[_InlineSpan, ...]
    align: str = "left"


@dataclass(slots=True, frozen=True)
class _TableRow:
    cells: tuple[_TableCell, ...]
    header: bool = False


@dataclass(slots=True)
class _Block:
    kind: str
    spans: tuple[_InlineSpan, ...] = ()
    indent: int = 0
    marker: str = ""
    rows: tuple[_TableRow, ...] = ()

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


def _make_markdown_parser():
    from markdown_it import MarkdownIt
    from mdit_py_plugins.dollarmath import dollarmath_plugin
    from mdit_py_plugins.texmath import texmath_plugin

    return (
        MarkdownIt("commonmark", {"html": False, "linkify": False})
        .enable("table")
        .use(texmath_plugin, delimiters="brackets")
        .use(dollarmath_plugin)
    )


def _normalize_block_math_boundaries(markdown_text: str) -> str:
    """Make standalone math delimiters block-safe without touching code fences."""

    lines = markdown_text.splitlines()
    normalized: list[str] = []
    fence: tuple[str, int] | None = None
    bracket_math_open = False
    dollar_math_open = False

    def ensure_blank() -> None:
        if normalized and normalized[-1].strip():
            normalized.append("")

    for index, line in enumerate(lines):
        fence_match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence_match:
            token = fence_match.group(1)
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
            normalized.append(line)
            continue
        if fence is not None:
            normalized.append(line)
            continue

        stripped = line.strip()
        is_bracket_open = stripped == r"\[" and not bracket_math_open
        is_bracket_close = stripped == r"\]" and bracket_math_open
        is_dollar_boundary = stripped == "$$"
        is_dollar_open = is_dollar_boundary and not dollar_math_open
        is_dollar_close = is_dollar_boundary and dollar_math_open

        if is_bracket_open or is_dollar_open:
            ensure_blank()
        normalized.append(line)

        if is_bracket_open:
            bracket_math_open = True
        elif is_bracket_close:
            bracket_math_open = False
        if is_dollar_boundary:
            dollar_math_open = not dollar_math_open

        if is_bracket_close or is_dollar_close:
            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            if next_line.strip():
                normalized.append("")

    return "\n".join(normalized)


def _inline_spans(node: Any, *, bold: bool = False, italic: bool = False) -> list[_InlineSpan]:
    out: list[_InlineSpan] = []
    node_type = node.type
    if node_type == "text":
        out.append(_InlineSpan(node.content, bold=bold, italic=italic))
    elif node_type in {"softbreak", "hardbreak"}:
        out.append(_InlineSpan("\n" if node_type == "hardbreak" else " ", bold=bold, italic=italic))
    elif node_type == "code_inline":
        out.append(_InlineSpan(node.content, kind="code"))
    elif node_type == "math_inline":
        out.append(_InlineSpan(node.content.strip(), kind="math"))
    elif node_type == "image":
        alt = "".join(span.text for child in node.children for span in _inline_spans(child))
        out.append(_InlineSpan(f"[图片: {alt or '未命名'}]", kind="link"))
    else:
        child_bold = bold or node_type == "strong"
        child_italic = italic or node_type == "em"
        child_kind = "link" if node_type == "link" else None
        for child in node.children or []:
            spans = _inline_spans(child, bold=child_bold, italic=child_italic)
            if child_kind:
                spans = [replace(span, kind=child_kind) if span.kind == "text" else span for span in spans]
            out.extend(spans)
    return out


def _node_spans(node: Any) -> tuple[_InlineSpan, ...]:
    inline = next((child for child in (node.children or []) if child.type == "inline"), None)
    source = inline.children if inline is not None else node.children
    spans: list[_InlineSpan] = []
    for child in source or []:
        spans.extend(_inline_spans(child))
    return _clean_spans(spans)


def _clean_spans(spans: Sequence[_InlineSpan]) -> tuple[_InlineSpan, ...]:
    cleaned: list[_InlineSpan] = []
    for span in spans:
        text = span.text if span.kind == "math" else _strip_unsupported_glyphs(span.text)
        if not text:
            continue
        candidate = replace(span, text=text)
        if (
            cleaned
            and candidate.kind == cleaned[-1].kind
            and candidate.bold == cleaned[-1].bold
            and candidate.italic == cleaned[-1].italic
        ):
            cleaned[-1] = replace(cleaned[-1], text=cleaned[-1].text + candidate.text)
        else:
            cleaned.append(candidate)

    if cleaned and cleaned[0].kind == "text":
        match = _TS_RE.match(cleaned[0].text)
        if match:
            prefix = cleaned[0].text[: match.end()]
            suffix = cleaned[0].text[match.end() :]
            first = replace(cleaned[0], text=prefix, kind="timestamp", bold=True)
            cleaned[:1] = [first, replace(cleaned[0], text=suffix)] if suffix else [first]
    return tuple(cleaned)


def _table_rows(node: Any) -> tuple[_TableRow, ...]:
    rows: list[_TableRow] = []

    def visit(current: Any, *, header: bool = False) -> None:
        is_header = header or current.type == "thead"
        if current.type == "tr":
            cells: list[_TableCell] = []
            for child in current.children or []:
                if child.type not in {"th", "td"}:
                    continue
                style = str((child.attrs or {}).get("style", ""))
                align = "right" if "right" in style else "center" if "center" in style else "left"
                cells.append(_TableCell(_node_spans(child), align))
            rows.append(_TableRow(tuple(cells), header=is_header))
            return
        for child in current.children or []:
            visit(child, header=is_header)

    visit(node)
    return tuple(rows)


def _parse_markdown_blocks(markdown_text: str) -> list[_Block]:
    """Parse Markdown into renderer-owned blocks using a CommonMark AST."""

    from markdown_it.tree import SyntaxTreeNode

    normalized_text = _normalize_block_math_boundaries(markdown_text)
    root = SyntaxTreeNode(_make_markdown_parser().parse(normalized_text))
    out: list[_Block] = []

    def visit(node: Any, *, list_depth: int = 0, quote: bool = False) -> None:
        node_type = node.type
        if node_type == "heading":
            level = int(str(node.tag)[1:]) if str(node.tag).startswith("h") else 3
            kind = "h1" if level == 1 else "h2" if level == 2 else "h3"
            out.append(_Block(kind, _node_spans(node)))
        elif node_type in {"paragraph", "block_text"}:
            out.append(_Block("quote" if quote else "p", _node_spans(node), indent=list_depth))
        elif node_type in {"bullet_list", "ordered_list"}:
            ordered = node_type == "ordered_list"
            start = int((node.attrs or {}).get("start", 1))
            for offset, item in enumerate(node.children or []):
                marker = f"{start + offset}." if ordered else "•"
                first_content = True
                for child in item.children or []:
                    if child.type in {"paragraph", "block_text"}:
                        kind = "li" if first_content else "p"
                        out.append(
                            _Block(
                                kind,
                                _node_spans(child),
                                indent=list_depth,
                                marker=marker if first_content else "",
                            )
                        )
                        first_content = False
                    elif child.type in {"bullet_list", "ordered_list"}:
                        visit(child, list_depth=list_depth + 1, quote=quote)
                    else:
                        visit(child, list_depth=list_depth + 1, quote=quote)
        elif node_type == "blockquote":
            for child in node.children or []:
                visit(child, list_depth=list_depth, quote=True)
        elif node_type == "math_block":
            out.append(_Block("math", (_InlineSpan(node.content.strip(), kind="math"),)))
        elif node_type in {"code_block", "fence"}:
            out.append(_Block("code", (_InlineSpan(node.content.rstrip(), kind="code"),), indent=list_depth))
        elif node_type == "table":
            out.append(_Block("table", rows=_table_rows(node)))
        elif node_type == "hr":
            out.append(_Block("hr"))
        else:
            for child in node.children or []:
                visit(child, list_depth=list_depth, quote=quote)

    for child in root.children:
        visit(child)
    return out


_MATH_LOCK = threading.Lock()
_MATH_DPI = 72
_MATH_PUNCTUATION = str.maketrans(
    {
        "、": r",\ ",
        "，": r",\ ",
        "。": r".\ ",
        "：": ":",
        "；": ";",
        "（": "(",
        "）": ")",
        "＋": "+",
        "－": "-",
        "＝": "=",
    }
)


def _normalize_math_formula(formula: str) -> str:
    compact = re.sub(r"\s*\n\s*", " ", formula.strip())
    return compact.translate(_MATH_PUNCTUATION)


@functools.lru_cache(maxsize=256)
def _math_bitmap_data(
    formula: str,
    font_size: int,
    color: tuple[int, int, int],
) -> tuple[bytes, int, int, int]:
    import numpy as np
    from matplotlib.font_manager import FontProperties
    from matplotlib.mathtext import MathTextParser
    from PIL import Image

    normalized = _normalize_math_formula(formula)
    if not normalized:
        raise ValueError("empty formula")
    with _MATH_LOCK:
        parsed = MathTextParser("agg").parse(
            f"${normalized}$",
            dpi=_MATH_DPI,
            prop=FontProperties(size=font_size),
        )
    alpha_array = np.asarray(parsed.image)
    alpha = Image.fromarray(alpha_array)
    rgba = Image.new("RGBA", alpha.size, (*color, 0))
    rgba.putalpha(alpha)
    baseline_ascent = round(parsed.height - parsed.depth)
    baseline_ascent = min(rgba.height, max(0, baseline_ascent))
    return rgba.tobytes(), rgba.width, rgba.height, baseline_ascent


def _render_math_image(
    formula: str,
    *,
    font_size: int,
    color: tuple[int, int, int],
    max_width: int,
) -> PILImage:
    from PIL import Image

    data, width, height, baseline_ascent = _math_bitmap_data(formula, font_size, color)
    image = Image.frombytes("RGBA", (width, height), data)
    if image.width > max_width:
        scale = max_width / image.width
        scaled_h = max(1, round(image.height * max_width / image.width))
        image = image.resize((max_width, scaled_h), Image.Resampling.LANCZOS)
        baseline_ascent = round(baseline_ascent * scale)
    image.info["baseline_ascent"] = min(image.height, max(0, baseline_ascent))
    return image


@dataclass(slots=True)
class _DrawRun:
    text: str = ""
    image: PILImage | None = None
    font: Any = None
    color: tuple[int, int, int] = (0, 0, 0)
    width: float = 0
    ascent: int = 0
    descent: int = 0
    bold: bool = False
    code: bool = False
    underline: bool = False


@dataclass(slots=True)
class _InlineLine:
    runs: list[_DrawRun]
    width: float
    height: int
    baseline: int


@dataclass(slots=True)
class _TableLayout:
    rows: list[list[list[_InlineLine]]]
    alignments: list[list[str]]
    row_heights: list[int]
    header_rows: set[int]
    column_width: int


@dataclass(slots=True)
class _ItemLayout:
    kind: str
    indent: int = 0
    marker: str = ""
    marker_width: int = 0
    lines: list[_InlineLine] | None = None
    image: PILImage | None = None
    table: _TableLayout | None = None
    height: int = 0


class PillowRenderer:
    """Render CommonMark and common TeX expressions into PNG cards."""

    BG = (26, 27, 46)
    CARD_BG = (30, 33, 64)
    CODE_BG = (18, 19, 42)
    QUOTE_BG = (38, 36, 72)
    TABLE_ALT_BG = (34, 38, 70)
    TITLE_FG = (241, 245, 249)
    TEXT_FG = (201, 206, 220)
    ACCENT_FG = (147, 197, 253)
    STRONG_FG = (249, 168, 212)
    EMPHASIS_FG = (103, 232, 249)
    CODE_FG = (252, 165, 165)
    TS_FG = (251, 146, 60)
    DIM_FG = (148, 163, 184)
    TITLE_SIZE = 28
    H2_SIZE = 20
    H3_SIZE = 18
    BODY_SIZE = 16
    PADDING = 40
    CARD_PADDING = 26
    CARD_GAP = 22
    BLOCK_GAP = 9
    STRIPE_W = 6
    LIST_INDENT = 24
    BULLET_INDENT = 28
    SUBSECTION_INDENT = 16
    FOOTER_H = 56

    def __init__(self, *, output_dir: str | Path, image_width: int = 900) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._width = image_width

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
            return self._render_one(markdown_text, base_filename, page_label=None, total=1)

        pages = split_by_chapters(markdown_text, max_cards=max_cards_per_image)
        outputs: list[Path] = []
        failed_pages: list[int] = []
        page_errors: dict[int, str] = {}
        total = len(pages)
        for idx, page in enumerate(pages, start=1):
            label = None if total == 1 else f"({idx}/{total})"
            try:
                outputs.extend(
                    self._render_one(page, f"{base_filename}_p{idx}", page_label=label, total=total)
                )
            except RenderError as exc:
                logger.warning(f"page {idx}/{total} Python render failed: {exc}")
                failed_pages.append(idx)
                page_errors[idx] = str(exc)
        if failed_pages and outputs:
            raise PartialRenderError(
                f"partial Python render failed; failed_pages={failed_pages}",
                generated_paths=outputs,
                failed_pages=failed_pages,
                page_errors=page_errors,
            )
        if not outputs:
            raise RenderError("all pages failed to render with Python renderer")
        return outputs

    def _render_one(
        self,
        markdown_text: str,
        base_filename: str,
        *,
        page_label: str | None,
        total: int,
    ) -> list[Path]:
        try:
            from PIL import Image, ImageDraw

            blocks = _parse_markdown_blocks(markdown_text)
        except ImportError as exc:  # pragma: no cover - installation failure
            raise RenderError(f"missing Python render dependency: {exc}") from exc
        except Exception as exc:
            raise RenderError(f"Markdown parse failed: {exc}") from exc

        if not blocks:
            blocks.append(_Block("p", (_InlineSpan("(空内容)"),)))

        title_block = next((block for block in blocks if block.kind == "h1"), None)
        body_blocks = [block for block in blocks if block is not title_block]
        title_text = title_block.text if title_block else "AI 视频总结"
        if page_label:
            title_text = f"{title_text} {page_label}"

        f_title, font_path = _load_font(self.TITLE_SIZE)
        f_h2, _ = _load_font(self.H2_SIZE)
        f_h3, _ = _load_font(self.H3_SIZE)
        f_body, _ = _load_font(self.BODY_SIZE)
        f_mono, _ = _load_font(self.BODY_SIZE, mono=True)
        fonts = {"title": f_title, "h2": f_h2, "h3": f_h3, "body": f_body, "mono": f_mono}

        content_w = self._width - self.PADDING * 2
        card_inner_w = content_w - self.CARD_PADDING * 2
        title_lines = self._wrap(title_text, font=f_title, max_width=content_w)
        title_adv = _line_advance(f_title)
        header_h = self.PADDING + len(title_lines) * title_adv + 24

        cards: list[dict[str, Any]] = []
        chapter_no = 0
        for idx, (heading, card_blocks) in enumerate(self._group_into_cards(body_blocks)):
            if heading is not None:
                chapter_no += 1
                badge = f"{chapter_no:02d}"
                badge_w = self._text_w(f_h2, badge + "  ")
                head_lines = self._wrap(heading, font=f_h2, max_width=max(1, card_inner_w - badge_w))
            else:
                badge, badge_w, head_lines = "", 0, []

            items = [self._layout_item(block, fonts, card_inner_w) for block in card_blocks]
            card_h = self.CARD_PADDING * 2
            if head_lines:
                card_h += len(head_lines) * _line_advance(f_h2) + 10
            card_h += sum(item.height + self.BLOCK_GAP for item in items)
            cards.append(
                {
                    "idx": idx,
                    "head_lines": head_lines,
                    "badge": badge,
                    "badge_w": badge_w,
                    "items": items,
                    "card_h": card_h,
                }
            )

        total_h = header_h + sum(card["card_h"] + self.CARD_GAP for card in cards) + self.FOOTER_H
        logger.debug(
            f"Python page layout: chars={len(markdown_text)} cards={len(cards)} "
            f"height={total_h} width={self._width} font={font_path}"
        )
        image = Image.new("RGB", (self._width, total_h), self.BG)
        draw = ImageDraw.Draw(image)

        ty = self.PADDING
        for line in title_lines:
            draw.text((self.PADDING, ty), line, fill=self.TITLE_FG, font=f_title)
            ty += title_adv
        underline_w = min(content_w, max(120, self._text_w(f_title, title_lines[0]))) if title_lines else 120
        draw.line(
            (self.PADDING, ty + 4, self.PADDING + underline_w, ty + 4),
            fill=self.ACCENT_FG,
            width=4,
        )

        y = header_h
        for card in cards:
            border, _ = card_color_for(card["idx"])
            border_rgb = self._hex_to_rgb(border)
            card_x0 = self.PADDING
            card_x1 = self._width - self.PADDING
            card_h = card["card_h"]
            draw.rounded_rectangle((card_x0, y, card_x1, y + card_h), radius=14, fill=self.CARD_BG)
            draw.rectangle((card_x0, y, card_x0 + self.STRIPE_W, y + card_h), fill=border_rgb)

            cx = card_x0 + self.CARD_PADDING
            cy = y + self.CARD_PADDING
            if card["head_lines"]:
                draw.text((cx, cy), card["badge"], fill=border_rgb, font=f_h2)
                for line_idx, line in enumerate(card["head_lines"]):
                    hx = cx + card["badge_w"] if line_idx == 0 else cx
                    draw.text((hx, cy), line, fill=self.TITLE_FG, font=f_h2)
                    cy += _line_advance(f_h2)
                cy += 10

            for item in card["items"]:
                self._draw_item(
                    image,
                    draw,
                    item,
                    x=cx,
                    y=cy,
                    max_width=card_inner_w,
                    fonts=fonts,
                )
                cy += item.height + self.BLOCK_GAP
            y += card_h + self.CARD_GAP

        footer = (
            f"Powered by biliVideo · Markdown + MathText · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if total > 1 and page_label:
            footer += f" · {page_label}"
        draw.text((self.PADDING, total_h - 32), footer, fill=self.DIM_FG, font=f_body)

        output = self._output_dir / f"{base_filename}.png"
        try:
            image.save(output, "PNG", optimize=True)
        except OSError as exc:
            raise RenderError(f"Pillow save failed: {exc}") from exc
        logger.info(f"Python rendered {output.name} ({output.stat().st_size} bytes)")
        return [output]

    def _layout_item(self, block: _Block, fonts: dict[str, Any], max_width: int) -> _ItemLayout:
        indent = block.indent * self.LIST_INDENT
        if block.kind == "h3":
            lines = self._layout_spans(block.spans, fonts, max_width, base="h3")
            return _ItemLayout("h3", lines=lines, height=self._lines_height(lines) + 5)
        if block.kind == "hr":
            return _ItemLayout("hr", height=18)
        if block.kind == "math":
            try:
                image = _render_math_image(
                    block.text,
                    font_size=self.H3_SIZE,
                    color=self.TITLE_FG,
                    max_width=max_width - 24,
                )
            except Exception as exc:
                logger.warning(f"formula render failed; falling back to source: {exc}")
                fallback = (_InlineSpan(block.text, kind="code"),)
                lines = self._layout_spans(fallback, fonts, max_width - 24)
                return _ItemLayout("code", lines=lines, height=self._lines_height(lines) + 20)
            return _ItemLayout("math", image=image, height=image.height + 24)
        if block.kind == "table":
            table = self._layout_table(block.rows, fonts, max_width)
            return _ItemLayout("table", table=table, height=sum(table.row_heights))

        marker_width = 0
        available = max_width - indent
        if block.kind == "li":
            marker_width = max(self.BULLET_INDENT, self._text_w(fonts["body"], block.marker) + 10)
            available -= marker_width
        elif block.kind in {"quote", "code"}:
            available -= 24
        lines = self._layout_spans(block.spans, fonts, max(1, available))
        padding = 18 if block.kind in {"quote", "code"} else 0
        return _ItemLayout(
            block.kind,
            indent=indent,
            marker=block.marker,
            marker_width=marker_width,
            lines=lines,
            height=self._lines_height(lines) + padding,
        )

    def _layout_spans(
        self,
        spans: Sequence[_InlineSpan],
        fonts: dict[str, Any],
        max_width: int,
        *,
        base: str = "body",
    ) -> list[_InlineLine]:
        lines: list[_InlineLine] = []
        runs: list[_DrawRun] = []
        line_width = 0.0
        base_ascent, base_descent = self._font_metrics(fonts[base])
        base_line_height = _line_advance(fonts[base])

        def build_line(line_runs: list[_DrawRun], width: float) -> _InlineLine:
            max_ascent = max((run.ascent for run in line_runs), default=base_ascent)
            max_descent = max((run.descent for run in line_runs), default=base_descent)
            natural_height = max_ascent + max_descent
            math_padding = 2 if any(run.image is not None for run in line_runs) else 0
            height = max(base_line_height, natural_height + math_padding)
            top_leading = max(0, (height - natural_height) // 2)
            return _InlineLine(line_runs, width, height, top_leading + max_ascent)

        def flush() -> None:
            nonlocal runs, line_width
            if runs:
                lines.append(build_line(runs, line_width))
            runs = []
            line_width = 0.0

        def append_text(char: str, span: _InlineSpan) -> None:
            nonlocal line_width
            font = fonts["mono"] if span.kind == "code" else fonts[base]
            color = (
                self.TS_FG
                if span.kind == "timestamp"
                else self.CODE_FG
                if span.kind == "code"
                else self.ACCENT_FG
                if span.kind == "link"
                else self.STRONG_FG
                if span.bold
                else self.EMPHASIS_FG
                if span.italic
                else self.TEXT_FG
            )
            signature = (font, color, span.bold, span.kind == "code", span.kind == "link")
            previous = runs[-1] if runs and runs[-1].image is None else None
            old_signature = (
                (
                    previous.font,
                    previous.color,
                    previous.bold,
                    previous.code,
                    previous.underline,
                )
                if previous is not None
                else None
            )
            can_merge = signature == old_signature
            horizontal_padding = 8 if span.kind == "code" else 0
            candidate_text = previous.text + char if can_merge and previous is not None else char
            candidate_width = self._text_length(font, candidate_text) + horizontal_padding
            added_width = (
                candidate_width - previous.width if can_merge and previous is not None else candidate_width
            )
            if runs and line_width + added_width > max_width:
                flush()
                previous = None
                can_merge = False
                candidate_text = char
                candidate_width = self._text_length(font, char) + horizontal_padding
                added_width = candidate_width
            if not runs and char.isspace():
                return
            if can_merge and previous is not None:
                previous.text = candidate_text
                previous.width = candidate_width
                line_width += added_width
                return
            ascent, descent = self._font_metrics(font)
            run = _DrawRun(
                text=char,
                font=font,
                color=color,
                width=candidate_width,
                ascent=ascent,
                descent=descent,
                bold=span.bold,
                code=span.kind == "code",
                underline=span.kind == "link",
            )
            runs.append(run)
            line_width += candidate_width

        for span in spans:
            if span.kind == "math":
                try:
                    math_image = _render_math_image(
                        span.text,
                        font_size=int(getattr(fonts[base], "size", self.BODY_SIZE)),
                        color=self.TITLE_FG,
                        max_width=max_width,
                    )
                except Exception as exc:
                    logger.warning(f"inline formula render failed; using source: {exc}")
                    for char in span.text:
                        append_text(char, replace(span, kind="code"))
                    continue
                if runs and line_width + math_image.width > max_width:
                    flush()
                math_ascent = int(math_image.info.get("baseline_ascent", math_image.height))
                runs.append(
                    _DrawRun(
                        image=math_image,
                        width=math_image.width,
                        ascent=math_ascent,
                        descent=math_image.height - math_ascent,
                    )
                )
                line_width += math_image.width
                continue
            for char in span.text:
                if char == "\n":
                    flush()
                else:
                    append_text(char, span)
        flush()
        return lines or [build_line([], 0)]

    def _layout_table(
        self,
        rows: Sequence[_TableRow],
        fonts: dict[str, Any],
        max_width: int,
    ) -> _TableLayout:
        column_count = max((len(row.cells) for row in rows), default=1)
        column_width = max(1, max_width // column_count)
        laid_out: list[list[list[_InlineLine]]] = []
        alignments: list[list[str]] = []
        heights: list[int] = []
        header_rows: set[int] = set()
        for row_idx, row in enumerate(rows):
            if row.header:
                header_rows.add(row_idx)
            cells: list[list[_InlineLine]] = []
            cell_alignments: list[str] = []
            for cell in row.cells:
                spans = tuple(replace(span, bold=True) for span in cell.spans) if row.header else cell.spans
                cells.append(self._layout_spans(spans, fonts, max(1, column_width - 16)))
                cell_alignments.append(cell.align)
            while len(cells) < column_count:
                cells.append([])
                cell_alignments.append("left")
            laid_out.append(cells)
            alignments.append(cell_alignments)
            heights.append(max((self._lines_height(lines) for lines in cells), default=0) + 16)
        return _TableLayout(laid_out, alignments, heights, header_rows, column_width)

    def _draw_item(
        self,
        image: PILImage,
        draw: Any,
        item: _ItemLayout,
        *,
        x: int,
        y: int,
        max_width: int,
        fonts: dict[str, Any],
    ) -> None:
        if item.kind == "hr":
            draw.line((x, y + 8, x + max_width, y + 8), fill=(71, 85, 105), width=1)
            return
        if item.kind == "math" and item.image is not None:
            px = x + max(0, (max_width - item.image.width) // 2)
            image.paste(item.image, (px, y + 10), item.image)
            return
        if item.kind == "table" and item.table is not None:
            self._draw_table(image, draw, item.table, x=x, y=y, max_width=max_width)
            return

        ix = x + item.indent
        content_y = y
        if item.kind == "h3":
            draw.rectangle((ix, y + 2, ix + 3, y + item.height - 2), fill=self.ACCENT_FG)
            ix += 12
        elif item.kind == "li":
            first_line = (item.lines or [None])[0]
            if item.marker == "•":
                radius = 3
                center_y = y + (first_line.height // 2 if first_line is not None else 12)
                draw.ellipse(
                    (ix + 4, center_y - radius, ix + 4 + radius * 2, center_y + radius),
                    fill=self.ACCENT_FG,
                )
            else:
                marker_baseline = y + (first_line.baseline if first_line is not None else 18)
                self._draw_text_at_baseline(
                    draw,
                    (ix, marker_baseline),
                    item.marker,
                    fill=self.ACCENT_FG,
                    font=fonts["body"],
                )
            ix += item.marker_width
        elif item.kind == "quote":
            draw.rounded_rectangle((ix, y, x + max_width, y + item.height), radius=7, fill=self.QUOTE_BG)
            draw.rectangle((ix, y, ix + 3, y + item.height), fill=(167, 139, 250))
            ix += 12
            content_y += 9
        elif item.kind == "code":
            draw.rounded_rectangle((ix, y, x + max_width, y + item.height), radius=7, fill=self.CODE_BG)
            ix += 12
            content_y += 9

        for line in item.lines or []:
            self._draw_inline_line(image, draw, line, ix, content_y)
            content_y += line.height

    def _draw_inline_line(self, image: PILImage, draw: Any, line: _InlineLine, x: int, y: int) -> None:
        cursor = float(x)
        baseline_y = y + line.baseline
        for run in line.runs:
            if run.image is not None:
                py = baseline_y - run.ascent
                image.paste(run.image, (round(cursor), py), run.image)
                cursor += run.width
                continue
            text_x = cursor
            if run.code:
                background_top = max(y, baseline_y - run.ascent - 2)
                background_bottom = min(y + line.height - 1, baseline_y + run.descent + 2)
                draw.rounded_rectangle(
                    (cursor, background_top, cursor + run.width, background_bottom),
                    radius=4,
                    fill=(58, 39, 57),
                )
                text_x += 4
            self._draw_text_at_baseline(
                draw,
                (round(text_x), baseline_y),
                run.text,
                fill=run.color,
                font=run.font,
            )
            if run.underline:
                underline_y = min(y + line.height - 2, baseline_y + 2)
                draw.line((text_x, underline_y, text_x + run.width, underline_y), fill=run.color, width=1)
            cursor += run.width

    @staticmethod
    def _draw_text_at_baseline(
        draw: Any,
        position: tuple[float, float],
        text: str,
        *,
        fill: tuple[int, int, int],
        font: Any,
    ) -> None:
        try:
            draw.text(position, text, fill=fill, font=font, anchor="ls")
        except (TypeError, ValueError):  # pragma: no cover - legacy bitmap fonts
            ascent, _ = PillowRenderer._font_metrics(font)
            draw.text((position[0], position[1] - ascent), text, fill=fill, font=font)

    def _draw_table(
        self,
        image: PILImage,
        draw: Any,
        table: _TableLayout,
        *,
        x: int,
        y: int,
        max_width: int,
    ) -> None:
        cursor_y = y
        for row_idx, (cells, row_height) in enumerate(zip(table.rows, table.row_heights, strict=False)):
            fill = (
                self.QUOTE_BG
                if row_idx in table.header_rows
                else self.TABLE_ALT_BG
                if row_idx % 2
                else self.CARD_BG
            )
            draw.rectangle((x, cursor_y, x + max_width, cursor_y + row_height), fill=fill)
            cursor_x = x
            for cell_idx, lines in enumerate(cells):
                cell_y = cursor_y + 8
                cell_width = (
                    max_width - table.column_width * cell_idx
                    if cell_idx == len(cells) - 1
                    else table.column_width
                )
                content_width = max(1, cell_width - 16)
                alignment = table.alignments[row_idx][cell_idx]
                for line in lines:
                    line_x = cursor_x + 8
                    if alignment == "right":
                        line_x += max(0, content_width - line.width)
                    elif alignment == "center":
                        line_x += max(0, (content_width - line.width) // 2)
                    self._draw_inline_line(image, draw, line, line_x, cell_y)
                    cell_y += line.height
                cursor_x += table.column_width
                if cell_idx < len(cells) - 1:
                    draw.line((cursor_x, cursor_y, cursor_x, cursor_y + row_height), fill=(71, 85, 105))
            draw.line(
                (x, cursor_y + row_height, x + max_width, cursor_y + row_height),
                fill=(71, 85, 105),
            )
            cursor_y += row_height

    @staticmethod
    def _lines_height(lines: Sequence[_InlineLine]) -> int:
        return sum(line.height for line in lines)

    @staticmethod
    def _font_metrics(font: Any) -> tuple[int, int]:
        try:
            ascent, descent = font.getmetrics()
            return max(1, int(ascent)), max(0, int(descent))
        except (AttributeError, OSError):
            size = max(1, int(getattr(font, "size", 16)))
            return size, max(1, size // 4)

    @staticmethod
    def _group_into_cards(blocks: Sequence[_Block]) -> list[tuple[str | None, list[_Block]]]:
        cards: list[tuple[str | None, list[_Block]]] = []
        current: list[_Block] = []
        current_heading: str | None = None
        for block in blocks:
            if block.kind == "h2":
                if current_heading is not None or current:
                    cards.append((current_heading, current))
                current = []
                current_heading = block.text
            else:
                current.append(block)
        cards.append((current_heading, current))
        return cards

    @staticmethod
    def _wrap(text: str, *, font: FreeTypeFont, max_width: int) -> list[str]:
        if not text:
            return [""]
        lines: list[str] = []
        current = ""
        current_w = 0.0
        for char in text:
            try:
                char_w = font.getlength(char)
            except Exception:
                char_w = int(getattr(font, "size", 16)) // 2
            if current and current_w + char_w > max_width:
                lines.append(current)
                current = char
                current_w = char_w
            else:
                current += char
                current_w += char_w
        if current:
            lines.append(current)
        return lines or [""]

    @staticmethod
    def _text_length(font: FreeTypeFont, text: str) -> float:
        try:
            return float(font.getlength(text))
        except Exception:
            try:
                bbox = font.getbbox(text)
                return float(bbox[2] - bbox[0])
            except Exception:
                return float(len(text) * (int(getattr(font, "size", 16)) // 2))

    @staticmethod
    def _text_w(font: FreeTypeFont, text: str) -> int:
        return math.ceil(PillowRenderer._text_length(font, text))

    @staticmethod
    def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
        value = hex_str.strip().lstrip("#")
        if len(value) == 3:
            value = "".join(char * 2 for char in value)
        if len(value) != 6 or any(char not in "0123456789abcdefABCDEF" for char in value):
            return PillowRenderer.ACCENT_FG
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
