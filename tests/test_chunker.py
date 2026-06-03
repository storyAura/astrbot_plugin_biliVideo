"""Chunker unit tests."""

from __future__ import annotations

from bilivideo.messaging.chunker import format_count, split_text_for_messages


class TestSplitTextForMessages:
    def test_short_unchanged(self) -> None:
        assert split_text_for_messages("hello", max_chunk=100) == ["hello"]

    def test_breaks_on_paragraph(self) -> None:
        text = "A" * 60 + "\n\n" + "B" * 60
        chunks = split_text_for_messages(text, max_chunk=70)
        assert len(chunks) == 2
        assert chunks[0].count("A") == 60
        assert chunks[1].count("B") == 60

    def test_falls_back_to_hard_cut(self) -> None:
        text = "X" * 100
        chunks = split_text_for_messages(text, max_chunk=40)
        assert len(chunks) >= 2
        assert sum(len(c) for c in chunks) == 100

    def test_no_newline_chunks_within_limit(self) -> None:
        text = "Y" * 250
        chunks = split_text_for_messages(text, max_chunk=40)
        assert all(len(c) <= 40 for c in chunks)
        assert "".join(chunks) == text

    def test_newline_near_start_produces_valid_chunks(self) -> None:
        text = "A\n" + "B" * 200
        chunks = split_text_for_messages(text, max_chunk=40)
        assert all(len(c) <= 40 for c in chunks)
        assert all(c for c in chunks)
        assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


class TestFormatCount:
    def test_small(self) -> None:
        assert format_count(123) == "123"

    def test_wan(self) -> None:
        assert format_count(15000) == "1.5万"

    def test_yi(self) -> None:
        assert format_count(150_000_000) == "1.5亿"
