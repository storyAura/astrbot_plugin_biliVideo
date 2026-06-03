"""Markdown pagination tests."""

from __future__ import annotations

from bilivideo.render.pagination import split_by_chapters


def _doc(chapter_count: int) -> str:
    parts = ["# 视频标题", "引言段落"]
    for i in range(chapter_count):
        parts.append(f"## 章节{i}")
        parts.append(f"内容{i}")
    return "\n".join(parts)


class TestSplitByChapters:
    def test_no_chapters(self) -> None:
        out = split_by_chapters("# Title\n\n本文无章节", max_cards=6)
        assert out == ["# Title\n\n本文无章节"]

    def test_single_page(self) -> None:
        out = split_by_chapters(_doc(3), max_cards=6)
        assert len(out) == 1
        assert out[0].startswith("# 视频标题")

    def test_multi_page(self) -> None:
        out = split_by_chapters(_doc(8), max_cards=6)
        assert len(out) == 2
        assert out[0].count("## 章节") == 6
        assert out[1].count("## 章节") == 2
        assert out[1].startswith("# 视频标题(续)")

    def test_chapter_intact_per_page(self) -> None:
        out = split_by_chapters(_doc(13), max_cards=5)
        assert len(out) == 3
        assert sum(p.count("## 章节") for p in out) == 13

    def test_splits_large_early_chapters_by_size(self) -> None:
        parts = ["# 视频标题", "引言段落"]
        for i in range(8):
            repeat = 500 if i < 2 else 20
            parts.append(f"## 章节{i}")
            parts.append("很长的内容" * repeat)

        out = split_by_chapters("\n".join(parts), max_cards=6, max_page_chars=2500)

        assert len(out) > 2
        assert out[0].count("## 章节") < 6
        assert all(page.startswith("# 视频标题") for page in out)
        for i in range(8):
            assert any(f"## 章节{i}" in page for page in out)
        assert any("(续)" in page for page in out)

    def test_splits_single_oversize_chapter(self) -> None:
        text = "# 视频标题\n\n## 超大章节\n" + ("长内容" * 2000)

        out = split_by_chapters(text, max_cards=6, max_page_chars=2500)

        assert len(out) > 1
        assert all(len(page) < 3500 for page in out)
        assert out[0].startswith("# 视频标题")
        assert out[1].startswith("# 视频标题(续)")

    def test_handles_document_starting_with_chapter(self) -> None:
        text = "## 第一章\n内容\n## 第二章\n内容"

        out = split_by_chapters(text, max_cards=1)

        assert len(out) == 2
        assert out[0].startswith("# AI 视频总结")
        assert out[0].count("## ") == 1

    def test_normalizes_crlf(self) -> None:
        text = "# 标题\r\n\r\n## 一\r\n内容\r\n## 二\r\n内容"

        out = split_by_chapters(text, max_cards=1)

        assert len(out) == 2
        assert "\r" not in out[0]
