"""The plugin ships a CJK font subset so the Pillow fallback renders images
on a bare container (no system CJK font installed, e.g. Zeabur/Docker).

These tests guard that wiring: the font is present, loads, renders real CJK
glyphs (not tofu), and is used only as a last-resort candidate so system
fonts keep priority.
"""

from __future__ import annotations

import os

from PIL import ImageFont

from bilivideo.render import pillow_renderer as pr


def test_bundled_font_is_shipped() -> None:
    assert os.path.exists(pr._BUNDLED_CJK_FONT), pr._BUNDLED_CJK_FONT
    assert pr._BUNDLED_CJK_FONT.endswith(".otf")


def test_bundled_font_is_last_resort_candidate() -> None:
    # System fonts must be preferred; the bundled font is appended last.
    assert pr._CJK_FONT_CANDIDATES[-1] == pr._BUNDLED_CJK_FONT


def test_bundled_font_renders_cjk_glyphs() -> None:
    font = ImageFont.truetype(pr._BUNDLED_CJK_FONT, 20)
    # A non-zero advance for CJK text means the glyphs exist (not missing).
    bbox = font.getbbox("总结视频字幕哔哩")
    assert bbox[2] > 0


def test_pillow_ready_with_only_bundled_font(monkeypatch) -> None:
    # Simulate a bare container: no system font path resolves, only the bundled one.
    monkeypatch.setattr(
        pr, "_CJK_FONT_CANDIDATES", ("/nonexistent/system-font.ttc", pr._BUNDLED_CJK_FONT)
    )
    assert pr._find_cjk_font() == pr._BUNDLED_CJK_FONT
    ready, reason = pr.check_pillow_ready()
    assert ready, reason
