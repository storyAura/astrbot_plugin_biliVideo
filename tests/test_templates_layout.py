"""wkhtml template layout + sanitizer hardening tests.

Guards the fixes for wkhtmltoimage's old WebKit engine: the H1 must stay
visible (no background-clip:text), the card layout must not rely on CSS Grid,
and `file:` URIs must be neutralized.
"""

from __future__ import annotations

import re

from bilivideo.render.templates import build_full_html, sanitize_html


def _style(html: str) -> str:
    match = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    assert match is not None
    return re.sub(r"\s+", "", match.group(1))


def _rule(style: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\{{([^}}]+)\}}", style)
    assert match is not None
    return match.group(1)


def _html(title: str = "标题") -> str:
    return build_full_html(
        "<div class='card'>x</div>", title_text=title, footer_time="t", width=1400
    )


class TestTitleAlwaysVisible:
    def test_no_background_clip_text(self) -> None:
        html = _html()
        assert "background-clip:text" not in html
        assert "-webkit-text-fill-color:transparent" not in html

    def test_keeps_solid_title_color(self) -> None:
        assert "color:#f1f5f9" in _html()

    def test_title_is_escaped(self) -> None:
        assert "&lt;script&gt;" in _html("<script>")


class TestEngineSafeLayout:
    def test_content_is_not_css_grid(self) -> None:
        html = _html()
        assert "display:grid" not in html
        assert "grid-template-columns" not in html

    def test_cards_use_single_column_blocks(self) -> None:
        style = _style(_html())
        card_rule = _rule(style, ".card,.card-intro")
        assert "float:left" not in card_rule
        assert "width:48%" not in card_rule
        assert "float:none" in card_rule
        assert "width:100%" in card_rule
        assert "clear:both" in card_rule

    def test_content_has_overflow_guards(self) -> None:
        style = _style(_html())
        body_rule = _rule(style, "body")
        image_rule = _rule(style, "img")
        pre_rule = _rule(style, "pre")
        table_rule = _rule(style, "table")
        cell_rule = _rule(style, "th,td")
        assert "overflow-wrap:anywhere" in body_rule
        assert "word-wrap:break-word" in body_rule
        assert "max-width:100%" in image_rule
        assert "height:auto" in image_rule
        assert "display:block" in image_rule
        assert "white-space:pre-wrap" in pre_rule
        assert "table-layout:fixed" in table_rule
        assert "overflow-wrap:anywhere" in cell_rule

    def test_custom_width_controls_canvas(self) -> None:
        html = build_full_html(
            "<div class='card'>x</div>", title_text="标题", footer_time="t", width=900
        )
        assert "width:900px" in html


class TestSanitizerBlocksFileScheme:
    def test_neutralizes_file_uri(self) -> None:
        out = sanitize_html('<img src="file:///etc/passwd">')
        assert "file:" not in out
        assert "unsafe:" in out

    def test_still_neutralizes_javascript(self) -> None:
        out = sanitize_html('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in out
        assert "unsafe:" in out
