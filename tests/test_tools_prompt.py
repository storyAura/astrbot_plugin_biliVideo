"""Combined summary prompt builder unit tests."""

from __future__ import annotations

from types import SimpleNamespace

from bilivideo.tools.registry import build_combined_summary_prompt


def _video(*, title: str | None, bvid: str, transcript: str) -> SimpleNamespace:
    info = SimpleNamespace(title=title) if title is not None else None
    return SimpleNamespace(info=info, bvid=bvid, transcript=transcript)


class TestBuildCombinedSummaryPrompt:
    def test_includes_titles_and_transcripts(self) -> None:
        successful = [
            _video(title="第一个视频", bvid="BV1aaa", transcript="转写内容一"),
            _video(title="第二个视频", bvid="BV2bbb", transcript="转写内容二"),
        ]
        prompt = build_combined_summary_prompt(successful)
        assert "第一个视频" in prompt
        assert "第二个视频" in prompt
        assert "转写内容一" in prompt
        assert "转写内容二" in prompt

    def test_uses_one_indexed_numbering(self) -> None:
        successful = [
            _video(title="A", bvid="BV1aaa", transcript="t1"),
            _video(title="B", bvid="BV2bbb", transcript="t2"),
        ]
        prompt = build_combined_summary_prompt(successful)
        assert "【视频 1】" in prompt
        assert "【视频 2】" in prompt

    def test_contains_markdown_instruction(self) -> None:
        prompt = build_combined_summary_prompt(
            [_video(title="A", bvid="BV1aaa", transcript="t1")]
        )
        assert "Markdown" in prompt

    def test_falls_back_to_bvid_when_info_missing(self) -> None:
        prompt = build_combined_summary_prompt(
            [_video(title=None, bvid="BV1noinfo", transcript="t1")]
        )
        assert "BV1noinfo" in prompt
