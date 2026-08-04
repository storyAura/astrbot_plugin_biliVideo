"""Post-processing unit tests."""

from __future__ import annotations

from bilivideo.summarize.post_process import replace_timestamp_markers, smart_truncate


class TestReplaceTimestampMarkers:
    def test_bracketed(self) -> None:
        out = replace_timestamp_markers("Look at *Content-[04:16]*")
        assert out == "Look at [04:16]"

    def test_heading_does_not_keep_trailing_emphasis_marker(self) -> None:
        out = replace_timestamp_markers("## 章节 *Content-[00:21]*")
        assert out == "## 章节 [00:21]"

    def test_unbracketed(self) -> None:
        out = replace_timestamp_markers("Content-04:16 ok")
        assert "[04:16]" in out

    def test_normalizes_single_digit_minutes(self) -> None:
        assert replace_timestamp_markers("Content-[2:03]") == "[02:03]"

    def test_keeps_hour_component(self) -> None:
        assert replace_timestamp_markers("Content-[1:02:03]") == "[1:02:03]"

    def test_invalid_seconds_are_left_visible(self) -> None:
        source = "Content-[01:99]"
        assert replace_timestamp_markers(source) == source

    def test_no_marker(self) -> None:
        text = "no markers here"
        assert replace_timestamp_markers(text) == text


class TestSmartTruncate:
    def test_short_unchanged(self) -> None:
        text = "hello"
        assert smart_truncate(text, 100) == text

    def test_truncates_to_paragraph(self) -> None:
        body = "段落一非常长且重要A\n\n段落二也是一段内容B\n\n段落三这一段会被剪掉"
        out = smart_truncate(body, 28)
        assert "段落一" in out
        assert "段落三" not in out
        assert "内容过长提示" in out

    def test_force_cut_when_no_paragraph(self) -> None:
        text = "a" * 200
        out = smart_truncate(text, 100)
        # at least keeps 70%
        assert len(out) >= 70
