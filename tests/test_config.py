"""Config validation tests."""

from __future__ import annotations

from bilivideo.core.config import PluginConfig


def test_defaults() -> None:
    cfg = PluginConfig.from_mapping({})
    assert cfg.note_style == "professional"
    assert cfg.max_cards_per_image == 6
    assert cfg.access_mode == "blacklist"
    assert "总结" in cfg.trigger_keywords


def test_invalid_enum_falls_back() -> None:
    cfg = PluginConfig.from_mapping({"note_style": "invalid"})
    assert cfg.note_style == "professional"


def test_int_clamps_within_range() -> None:
    cfg = PluginConfig.from_mapping({"max_note_length": 99})
    assert cfg.max_note_length == 500  # clamped to lo=500
    cfg = PluginConfig.from_mapping({"max_note_length": 99999})
    assert cfg.max_note_length == 12000  # clamped to hi


def test_csv_split() -> None:
    cfg = PluginConfig.from_mapping({"push_groups": "100,200,abc, 300 "})
    assert cfg.push_groups == ("100", "200", "300")  # 'abc' filtered (not isdigit)


def test_trigger_keywords_custom() -> None:
    cfg = PluginConfig.from_mapping({"trigger_keywords": "abc,def"})
    assert cfg.trigger_keywords == ("abc", "def")


def test_openai_compatible_predicate() -> None:
    cfg = PluginConfig.from_mapping(
        {
            "llm_provider": "openai_compatible",
            "llm_api_base": "https://x/v1",
            "llm_api_key": "sk-x",
        }
    )
    assert cfg.is_openai_compatible
    assert cfg.has_llm_credentials()


def test_nested_groups_are_flattened() -> None:
    cfg = PluginConfig.from_mapping(
        {
            "general": {"debug_mode": True, "processing_timeout": 120},
            "llm": {"llm_provider": "openai_compatible"},
            "experimental": {"enable_multi_platform": True},
        }
    )
    assert cfg.debug_mode is True
    assert cfg.processing_timeout == 120
    assert cfg.llm_provider == "openai_compatible"
    assert cfg.enable_multi_platform is True


def test_flat_config_still_supported() -> None:
    # legacy flat layout must keep working alongside the new nested groups
    cfg = PluginConfig.from_mapping({"debug_mode": True, "max_note_length": 800})
    assert cfg.debug_mode is True
    assert cfg.max_note_length == 800
