"""HTML templating used by the wkhtmltopdf-backed renderer.

We embed JetBrains Mono fonts as base64 inside `<style>` so the resulting
PNG renders identically regardless of the system fonts available to
wkhtmltopdf. The cache prevents repeatedly base64-encoding the fonts on
every render.
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

from ..core.logging import get_logger
from .theme import card_color_for

logger = get_logger("BiliVideo/Templates")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FONTS_DIR = _REPO_ROOT / "fonts"
_ASSETS_DIR = _REPO_ROOT / "assets"

_FONT_MAP = {
    "JetBrainsMono-Light.ttf": ("JetBrains Mono", "300"),
    "JetBrainsMono-Bold.ttf": ("JetBrains Mono", "700"),
    "JetBrainsMono-Thin.ttf": ("JetBrains Mono", "100"),
}

_font_face_cache: str | None = None
_logo_cache: str | None = None


def _build_font_faces() -> str:
    global _font_face_cache
    if _font_face_cache is not None:
        return _font_face_cache

    blocks: list[str] = []
    for filename, (family, weight) in _FONT_MAP.items():
        path = _FONTS_DIR / filename
        if not path.exists():
            logger.warning(f"font missing: {path}")
            continue
        try:
            data = base64.b64encode(path.read_bytes()).decode()
        except OSError as exc:
            logger.warning(f"font read failed ({path}): {exc}")
            continue
        blocks.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-display:swap;"
            f"src:url(data:font/truetype;base64,{data}) format('truetype')}}"
        )
    _font_face_cache = "\n".join(blocks)
    return _font_face_cache


def get_logo_base64() -> str:
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache
    path = _ASSETS_DIR / "logo.png"
    if not path.exists():
        path = _REPO_ROOT / "logo.png"
    if not path.exists():
        _logo_cache = ""
        return ""
    try:
        data = base64.b64encode(path.read_bytes()).decode()
        _logo_cache = f"data:image/png;base64,{data}"
    except OSError as exc:
        logger.warning(f"logo read failed: {exc}")
        _logo_cache = ""
    return _logo_cache


# Risky tags whose inner content must also be discarded.
_RISKY_PAIRED_TAGS = ("script", "style", "iframe", "object")
# Risky tags that are stripped (tag only) wherever they appear.
_RISKY_TAGS = (
    "iframe",
    "object",
    "embed",
    "link",
    "meta",
    "base",
    "form",
    "frame",
    "frameset",
)
# Schemes that can execute or read local files when placed in an href/src
# attribute (`file:` matters even with JavaScript disabled: wkhtmltoimage still
# fetches resources, so a crafted <img src="file:///…"> could read host files).
_DANGEROUS_SCHEME_RE = re.compile(r"(?i)\b(?:javascript|vbscript|file):")
# Inline event handlers: on<word>= followed by a quoted or bare value.
_EVENT_HANDLER_RE = re.compile(
    r"""(?ix)            # case-insensitive, verbose
    \s+on\w+            # the on<event> attribute name
    \s*=\s*
    (?:"[^"]*"          # double-quoted value
       |'[^']*'         # single-quoted value
       |[^\s>]+)        # unquoted value
    """
)


def sanitize_html(html: str) -> str:
    """Defensively strip dangerous constructs from rendered HTML.

    Uses stdlib `re` only as defense-in-depth for the wkhtml renderer:
    LLM-authored Markdown may embed raw HTML that python-markdown passes
    through unescaped. We drop `<script>`/`<style>` blocks (with content),
    a set of risky tags, inline `on*` event handlers, and `javascript:`/
    `vbscript:` URIs, while leaving ordinary formatting tags untouched.
    """

    # 1. Remove paired risky tags together with their inner content.
    for tag in _RISKY_PAIRED_TAGS:
        html = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}\s*>",
            "",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # Also drop any unmatched opening/closing tag left behind.
        html = re.sub(rf"</?{tag}\b[^>]*>", "", html, flags=re.IGNORECASE)

    # 2. Strip remaining risky tags (opening, closing, self-closing).
    for tag in _RISKY_TAGS:
        html = re.sub(rf"</?{tag}\b[^>]*/?>", "", html, flags=re.IGNORECASE)

    # 3. Remove inline event-handler attributes (onclick, onerror, ...).
    html = _EVENT_HANDLER_RE.sub("", html)

    # 4. Neutralize javascript:/vbscript: URIs in any attribute value.
    html = _DANGEROUS_SCHEME_RE.sub("unsafe:", html)

    return html


def highlight_timestamps(html: str) -> str:
    """Wrap stand-alone timestamps in pill-style spans."""

    html = re.sub(r"⏱\s*(\d{1,2}:\d{2})", r'<span class="ts">⏱ \1</span>', html)
    html = re.sub(r"\[(\d{1,2}:\d{2})\]", r'<span class="ts">⏱ \1</span>', html)
    # remove orphaned timestamp paragraphs sitting right after an h2 heading
    html = re.sub(
        r"(</h2>\s*)<p>\s*<span class=\"ts\">[^<]*</span>\s*\*?\s*</p>",
        r"\1",
        html,
    )
    return html


def extract_title(html: str) -> tuple[str, str]:
    """Return `(title, html_without_h1)`. Falls back to a default title."""

    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    if not match:
        return "AI 视频总结", html

    title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
    body = html[: match.start()] + html[match.end() :]

    clean_title = re.sub(r"[📑📝🎬🎥\s]", "", title)
    if clean_title:
        dup_pattern = r"<p[^>]*>[^<]*" + re.escape(clean_title[:20]) + r"[^<]*</p>"
        body = re.sub(dup_pattern, "", body, count=1)

    if " - " in title:
        head, tail = title.rsplit(" - ", 1)
        title = f"{head} —— {tail}"
    return title, body


def wrap_chapters_in_cards(html: str) -> str:
    """Wrap each `<h2>` block into a colored card."""

    parts = re.split(r"(<h2[^>]*>.*?</h2>)", html, flags=re.DOTALL | re.IGNORECASE)
    if len(parts) <= 1:
        return f'<div class="card card-0">{html}</div>'

    pieces: list[str] = []
    intro = parts[0].strip()
    if intro:
        pieces.append(f'<div class="card-intro">{intro}</div>')

    card_idx = 0
    i = 1
    while i < len(parts):
        h2 = parts[i] if i < len(parts) else ""
        body = parts[i + 1] if i + 1 < len(parts) else ""
        border, bg = card_color_for(card_idx)
        pieces.append(
            f'<div class="card card-{card_idx % 6}" '
            f'style="border-left-color:{border};background:{bg}">{h2}{body}</div>'
        )
        card_idx += 1
        i += 2
    return "\n".join(pieces)


_BASE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei','PingFang SC','Noto Sans SC','Hiragino Sans GB',sans-serif;
     background:#1a1b2e;color:#c9cedc;width:__WIDTH__px;line-height:1.85;font-size:15px}
.header{background:linear-gradient(135deg,#1e2140 0%,#252250 30%,#1a2744 70%,#1e2140 100%);
        padding:40px 56px 32px;border-bottom:2px solid rgba(139,92,246,.25);position:relative;
        overflow:hidden;text-align:center}
.header::before{content:'';position:absolute;top:0;left:0;right:0;bottom:0;
        background:radial-gradient(ellipse at 70% 0%,rgba(96,165,250,.14) 0%,transparent 55%),
                   radial-gradient(ellipse at 30% 100%,rgba(139,92,246,.12) 0%,transparent 55%);
        pointer-events:none}
.header h1{position:relative;z-index:1;font-size:28px;font-weight:800;color:#f1f5f9;margin:0 auto;
           line-height:1.4;letter-spacing:.5px;max-width:90%}
.header-line{position:relative;z-index:1;width:80px;height:3px;margin:14px auto 0;
             background:linear-gradient(90deg,#60a5fa,#8b5cf6);border-radius:2px}
.content{padding:28px 40px 20px}
.content::after{content:'';display:block;clear:both}
.card,.card-intro{background:rgba(30,33,64,.82);border-radius:12px;
                   border:1px solid rgba(148,163,184,.08);border-left:4px solid #60a5fa;
                   padding:20px 24px;box-shadow:0 2px 8px rgba(0,0,0,.25);
                   float:left;width:48%;margin:0 1% 20px}
.card-intro{float:none;width:98%;clear:both;border-left-color:#a5f3c4;background:rgba(52,211,153,.10)}
h1{font-size:22px;font-weight:700;color:#e2e8f0;margin-bottom:12px}
h2{font-size:16px;font-weight:700;color:#e2e8f0;margin:-20px -24px 14px;padding:12px 24px 10px;
   border-radius:12px 12px 0 0;background:rgba(0,0,0,.18);
   border-bottom:1px solid rgba(148,163,184,.08);display:flex;align-items:center;gap:8px;
   letter-spacing:.3px}
h2::before{content:'';display:inline-block;width:8px;height:8px;border-radius:50%;
           background:currentColor;opacity:.6;flex-shrink:0;margin-right:8px;vertical-align:middle}
h3{font-size:15px;font-weight:700;color:#93c5fd;margin-top:16px;margin-bottom:8px;
   padding-left:12px;border-left:3px solid rgba(96,165,250,.4)}
h4,h5,h6{font-size:14px;font-weight:600;color:#c4b5fd;margin-top:12px;margin-bottom:6px}
p{margin-bottom:10px;text-align:justify;word-break:break-word;font-size:14px}
strong{color:#f9a8d4;font-weight:700}
em{color:#67e8f9;font-style:italic}
.ts{display:inline-block;background:rgba(251,146,60,.15);color:#fb923c;font-weight:700;
    font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid rgba(251,146,60,.3);
    margin:0 2px;font-family:'JetBrains Mono',monospace;letter-spacing:.5px}
ul,ol{margin-bottom:10px;padding-left:20px}
li{margin-bottom:5px;line-height:1.7;padding-left:4px;font-size:14px}
li::marker{color:#60a5fa;font-weight:700}
blockquote{background:rgba(139,92,246,.08);border-left:3px solid #8b5cf6;
           border-radius:0 10px 10px 0;padding:12px 18px;margin:12px 0;color:#a5b4fc;
           box-shadow:0 2px 6px rgba(139,92,246,.08)}
blockquote p{margin-bottom:4px}
code{background:rgba(248,113,113,.1);color:#fca5a5;padding:2px 6px;border-radius:6px;
     font-size:13px;font-family:'JetBrains Mono',monospace}
pre{background:#12132a;color:#e2e8f0;padding:12px 16px;border-radius:10px;margin:10px 0;
    font-size:13px;line-height:1.5;border:1px solid rgba(148,163,184,.1);
    box-shadow:inset 0 1px 4px rgba(0,0,0,.3)}
pre code{background:transparent;color:inherit;padding:0}
hr{border:none;height:1px;
   background:linear-gradient(to right,transparent,rgba(148,163,184,.2),transparent);margin:16px 0}
table{width:100%;border-collapse:collapse;margin:10px 0;border-radius:8px;overflow:hidden}
th{background:rgba(96,165,250,.12);color:#93c5fd;font-weight:700;padding:8px 12px;
   text-align:left;border-bottom:2px solid rgba(96,165,250,.2);font-size:14px}
td{padding:6px 12px;border-bottom:1px solid rgba(148,163,184,.08);font-size:14px}
tr:nth-child(even) td{background:rgba(148,163,184,.03)}
.footer{padding:14px 40px;border-top:1px solid rgba(148,163,184,.1);background:rgba(0,0,0,.1)}
.footer::after{content:'';display:block;clear:both}
.ftxt{float:left;font-size:11px;color:#64748b;letter-spacing:.8px;font-family:'JetBrains Mono',monospace}
.ftxt .br{color:#94a3b8;font-weight:600}
.ftime{float:right;font-size:11px;color:#4a5568;letter-spacing:.5px;font-family:'JetBrains Mono',monospace}
"""


def build_full_html(
    body_html: str,
    *,
    title_text: str,
    footer_time: str,
    width: int = 1400,
) -> str:
    css = _BASE_CSS.replace("__WIDTH__", str(width))
    fonts = _build_font_faces()
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<style>{fonts}{css}</style></head><body>"
        f"<div class=\"header\"><h1>{html.escape(title_text)}</h1><div class=\"header-line\"></div></div>"
        f"<div class=\"content\">{body_html}</div>"
        "<div class=\"footer\">"
        "<div class=\"ftxt\">Powered by <span class=\"br\">biliVideo</span> · AI 视频总结助手</div>"
        f"<div class=\"ftime\">{footer_time}</div>"
        "</div></body></html>"
    )
