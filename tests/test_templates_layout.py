"""wkhtml template layout + sanitizer hardening tests.

Guards the fixes for wkhtmltoimage's old WebKit engine: the H1 must stay
visible (no background-clip:text), the card layout must not rely on CSS Grid,
and `file:` URIs must be neutralized.
"""

from __future__ import annotations

from bilivideo.render.templates import build_full_html, sanitize_html


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

    def test_cards_use_float_columns(self) -> None:
        assert "float:left" in _html()


class TestSanitizerBlocksFileScheme:
    def test_neutralizes_file_uri(self) -> None:
        out = sanitize_html('<img src="file:///etc/passwd">')
        assert "file:" not in out
        assert "unsafe:" in out

    def test_still_neutralizes_javascript(self) -> None:
        out = sanitize_html('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in out
        assert "unsafe:" in out
