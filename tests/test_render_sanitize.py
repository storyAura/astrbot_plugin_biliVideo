"""HTML sanitization unit tests for the wkhtml renderer."""

from __future__ import annotations

from bilivideo.render.templates import sanitize_html


class TestRemovesDangerousConstructs:
    def test_strips_script_block(self) -> None:
        out = sanitize_html("<p>hi</p><script>alert(1)</script>")
        assert "<script" not in out
        assert "alert(1)" not in out

    def test_strips_style_block(self) -> None:
        out = sanitize_html("<style>body{display:none}</style><p>hi</p>")
        assert "<style" not in out
        assert "display:none" not in out

    def test_strips_event_handler_attributes(self) -> None:
        out = sanitize_html(
            '<img src="x" onerror="alert(1)"><button onclick=\'go()\'>x</button>'
        )
        assert "onerror" not in out
        assert "onclick" not in out
        assert "alert(1)" not in out
        assert "go()" not in out

    def test_neutralizes_javascript_href(self) -> None:
        out = sanitize_html('<a href="javascript:alert(1)">click</a>')
        assert "javascript:" not in out
        assert "unsafe:" in out

    def test_removes_iframe_with_content(self) -> None:
        out = sanitize_html('<iframe src="http://evil.example">danger</iframe>')
        assert "<iframe" not in out
        assert "danger" not in out


class TestPreservesOrdinaryTags:
    def test_keeps_strong(self) -> None:
        out = sanitize_html("<strong>bold</strong>")
        assert "<strong>bold</strong>" in out

    def test_keeps_heading(self) -> None:
        out = sanitize_html("<h2>Chapter</h2>")
        assert "<h2>Chapter</h2>" in out

    def test_keeps_list_item(self) -> None:
        out = sanitize_html("<ul><li>point</li></ul>")
        assert "<li>point</li>" in out

    def test_keeps_safe_anchor(self) -> None:
        out = sanitize_html('<a href="https://example.com">link</a>')
        assert '<a href="https://example.com">link</a>' in out
