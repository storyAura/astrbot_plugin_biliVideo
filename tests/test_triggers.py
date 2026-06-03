"""TriggerSet behavior."""

from __future__ import annotations

from bilivideo.parsing.triggers import DEFAULT_TRIGGER_KEYWORDS, TriggerSet


def test_default_keywords_match_chinese() -> None:
    triggers = TriggerSet(DEFAULT_TRIGGER_KEYWORDS)
    assert triggers.matches("帮我总结一下")
    assert triggers.matches("分析一下")
    assert not triggers.matches("好的")


def test_default_keywords_match_english_lowercase() -> None:
    triggers = TriggerSet(DEFAULT_TRIGGER_KEYWORDS)
    assert triggers.matches("please summarize")
    assert triggers.matches("Watch this")  # case-insensitive


def test_custom_keywords_replace_defaults() -> None:
    triggers = TriggerSet(["梗", "笑死"])
    assert triggers.matches("这个梗太好笑")
    assert triggers.matches("笑死了")
    assert not triggers.matches("总结一下")


def test_blank_input_falls_back_to_defaults() -> None:
    triggers = TriggerSet(["", "  "])
    assert "总结" in triggers.keywords  # fell back
    assert triggers.matches("帮我总结")


def test_has_bilibili_hint() -> None:
    assert TriggerSet.has_bilibili_hint("分享 https://b23.tv/abc")
    assert TriggerSet.has_bilibili_hint("BV1xx411c7mD")
    assert not TriggerSet.has_bilibili_hint("hello world")
