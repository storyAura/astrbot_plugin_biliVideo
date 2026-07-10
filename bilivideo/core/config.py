"""Strongly-typed configuration view over the raw dict supplied by AstrBot.

The plugin previously read every option via `self.config.get("foo", default)`
strewn across ~2,000 lines. This module consolidates all configuration
access points, performs validation/normalization once at startup, and then
exposes a frozen dataclass so the rest of the code never has to second-guess
defaults or types.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field
from typing import Any

from .constants import ACCESS_MODES, LLM_PROVIDERS, NOTE_STYLES, QUALITY_TO_KBPS

# Default trigger keywords kept here so it can be exercised in tests without
# dragging in the rest of the plugin.
_DEFAULT_TRIGGER_KEYWORDS = (
    "总结,看看,看一下,看下,分析,讲的啥,讲什么,说的啥,说什么,内容,视频,这个,这视频,"
    "帮我看,帮忙看,解析,翻译,summary,summarize,analyze,video,watch,check,see"
)


def _coerce_bool(raw: Any, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def _coerce_int(raw: Any, default: int, *, lo: int | None = None, hi: int | None = None) -> int:
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def _coerce_float(raw: Any, default: float) -> float:
    try:
        return float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _coerce_str(raw: Any, default: str, *, options: tuple[str, ...] | None = None) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return default
    value = raw.strip()
    if options and value not in options:
        return default
    return value


def _coerce_url_base(raw: Any) -> str:
    """Normalize an HTTP(S) base URL, blanking malformed/non-http values.

    A non-empty value that does not start with `http://` or `https://` is
    dropped to `""` so it can't be used as a malformed or SSRF-prone base.
    """

    value = _coerce_str(raw, "").rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        return ""
    return value


def _split_csv(raw: Any) -> tuple[str, ...]:
    """Split a 'a,b,c' style string into a tuple of stripped non-empty pieces."""

    if not raw:
        return ()
    if isinstance(raw, (list, tuple)):
        return tuple(str(x).strip() for x in raw if str(x).strip())
    return tuple(part.strip() for part in str(raw).split(",") if part.strip())


def _flatten_groups(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Collapse one level of nested config groups into a flat dict.

    AstrBot renders ``type: object`` schema entries as collapsible groups and
    hands the plugin back a nested mapping (``config[group][key]``). Values
    that are themselves mappings are treated as such groups and have their
    leaf keys lifted to the top level; scalar values pass through untouched.
    Every leaf key is globally unique, so this keeps both the new nested
    layout and any legacy flat config working.
    """

    flat: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, Mapping):
            for sub_key, sub_value in value.items():
                flat[sub_key] = sub_value
        else:
            flat[key] = value
    return flat


@dataclass(slots=True, frozen=True)
class PluginConfig:
    """Validated, immutable view of the plugin configuration."""

    # general -----------------------------------------------------------
    debug_mode: bool = False
    processing_timeout: int = 300
    user_cooldown_seconds: int = 8

    # llm ----------------------------------------------------------------
    llm_provider: str = "astrbot"
    llm_provider_id: str = ""
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.4

    # summary ------------------------------------------------------------
    note_style: str = "professional"
    enable_link: bool = True
    enable_summary: bool = True
    max_note_length: int = 3000
    prefer_subtitle: bool = True
    download_quality: str = "fast"
    enable_multi_platform: bool = False
    subtitle_langs: tuple[str, ...] = ("zh-Hans", "zh", "zh-CN", "ai-zh", "en", "en-US")

    # rendering ----------------------------------------------------------
    output_image: bool = True
    enable_auto_split: bool = True
    max_cards_per_image: int = 6
    image_width: int = 900

    # messaging ----------------------------------------------------------
    enable_forward_message: bool = False
    forward_bot_name: str = "BiliVideo 助手"
    forward_bot_uin: str = "0"
    platform_prefix: str = "aiocqhttp"

    # auto detect --------------------------------------------------------
    enable_miniapp_detect: bool = False
    detect_show_cover: bool = True
    detect_show_uploader: bool = True
    detect_show_desc: bool = True
    detect_show_pubtime: bool = True
    detect_show_link: bool = True
    detect_show_stats: bool = True
    detect_auto_summary: bool = False
    trigger_keywords: tuple[str, ...] = field(
        default_factory=lambda: tuple(_DEFAULT_TRIGGER_KEYWORDS.split(","))
    )

    # subscription -------------------------------------------------------
    enable_auto_push: bool = False
    auto_push_summary: bool = True
    check_interval_minutes: int = 600
    max_subscriptions: int = 20
    push_groups: tuple[str, ...] = ()
    push_users: tuple[str, ...] = ()

    # access -------------------------------------------------------------
    access_mode: str = "blacklist"
    group_list: tuple[str, ...] = ()

    # search -------------------------------------------------------------
    default_count: int = 20
    default_download_count: int = 3
    search_max_concurrent: int = 1
    search_show_progress: bool = True

    # ------------------------------------------------------------------
    # parsing / accessors
    # ------------------------------------------------------------------
    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> PluginConfig:
        """Build from the raw config dict supplied by AstrBot.

        The schema groups options into nested ``type: object`` sections, so
        the incoming mapping is nested (``config[group][key]``). We flatten it
        first; legacy flat configs flow through ``_flatten_groups`` unchanged.
        """

        flat = _flatten_groups(raw)
        d = cls._default
        return cls(
            debug_mode=_coerce_bool(flat.get("debug_mode"), d("debug_mode")),
            processing_timeout=_coerce_int(
                flat.get("processing_timeout"), d("processing_timeout"), lo=60, hi=1800
            ),
            user_cooldown_seconds=_coerce_int(
                flat.get("user_cooldown_seconds"), d("user_cooldown_seconds"), lo=0, hi=600
            ),
            llm_provider=_coerce_str(flat.get("llm_provider"), d("llm_provider"), options=LLM_PROVIDERS),
            llm_provider_id=_coerce_str(flat.get("llm_provider_id"), d("llm_provider_id")),
            llm_api_base=_coerce_url_base(flat.get("llm_api_base")),
            llm_api_key=_coerce_str(flat.get("llm_api_key"), d("llm_api_key")),
            llm_model=_coerce_str(flat.get("llm_model"), d("llm_model")),
            llm_temperature=_coerce_float(flat.get("llm_temperature"), d("llm_temperature")),
            note_style=_coerce_str(flat.get("note_style"), d("note_style"), options=NOTE_STYLES),
            enable_link=_coerce_bool(flat.get("enable_link"), d("enable_link")),
            enable_summary=_coerce_bool(flat.get("enable_summary"), d("enable_summary")),
            max_note_length=_coerce_int(
                flat.get("max_note_length"), d("max_note_length"), lo=500, hi=12000
            ),
            prefer_subtitle=_coerce_bool(flat.get("prefer_subtitle"), d("prefer_subtitle")),
            download_quality=_coerce_str(
                flat.get("download_quality"), d("download_quality"),
                options=tuple(QUALITY_TO_KBPS.keys()),
            ),
            enable_multi_platform=_coerce_bool(
                flat.get("enable_multi_platform"), d("enable_multi_platform")
            ),
            subtitle_langs=_split_csv(flat.get("subtitle_langs")) or d("subtitle_langs"),
            output_image=_coerce_bool(flat.get("output_image"), d("output_image")),
            enable_auto_split=_coerce_bool(flat.get("enable_auto_split"), d("enable_auto_split")),
            max_cards_per_image=_coerce_int(
                flat.get("max_cards_per_image"), d("max_cards_per_image"), lo=2, hi=12
            ),
            image_width=_coerce_int(flat.get("image_width"), d("image_width"), lo=800, hi=2400),
            enable_forward_message=_coerce_bool(
                flat.get("enable_forward_message"), d("enable_forward_message")
            ),
            forward_bot_name=_coerce_str(flat.get("forward_bot_name"), d("forward_bot_name")),
            forward_bot_uin=_coerce_str(flat.get("forward_bot_uin"), d("forward_bot_uin")),
            platform_prefix=_coerce_str(flat.get("platform_prefix"), d("platform_prefix")),
            enable_miniapp_detect=_coerce_bool(
                flat.get("enable_miniapp_detect"), d("enable_miniapp_detect")
            ),
            detect_show_cover=_coerce_bool(flat.get("detect_show_cover"), d("detect_show_cover")),
            detect_show_uploader=_coerce_bool(
                flat.get("detect_show_uploader"), d("detect_show_uploader")
            ),
            detect_show_desc=_coerce_bool(flat.get("detect_show_desc"), d("detect_show_desc")),
            detect_show_pubtime=_coerce_bool(flat.get("detect_show_pubtime"), d("detect_show_pubtime")),
            detect_show_link=_coerce_bool(flat.get("detect_show_link"), d("detect_show_link")),
            detect_show_stats=_coerce_bool(flat.get("detect_show_stats"), d("detect_show_stats")),
            detect_auto_summary=_coerce_bool(flat.get("detect_auto_summary"), d("detect_auto_summary")),
            trigger_keywords=_split_csv(flat.get("trigger_keywords")) or d("trigger_keywords"),
            enable_auto_push=_coerce_bool(flat.get("enable_auto_push"), d("enable_auto_push")),
            auto_push_summary=_coerce_bool(flat.get("auto_push_summary"), d("auto_push_summary")),
            check_interval_minutes=_coerce_int(
                flat.get("check_interval_minutes"), d("check_interval_minutes"), lo=5, hi=1440
            ),
            max_subscriptions=_coerce_int(
                flat.get("max_subscriptions"), d("max_subscriptions"), lo=1, hi=100
            ),
            push_groups=tuple(g for g in _split_csv(flat.get("push_groups")) if g.isdigit()),
            push_users=tuple(u for u in _split_csv(flat.get("push_users")) if u.isdigit()),
            access_mode=_coerce_str(flat.get("access_mode"), d("access_mode"), options=ACCESS_MODES),
            group_list=_split_csv(flat.get("group_list")),
            default_count=_coerce_int(flat.get("default_count"), d("default_count"), lo=1, hi=50),
            default_download_count=_coerce_int(
                flat.get("default_download_count"), d("default_download_count"), lo=1, hi=20
            ),
            search_max_concurrent=_coerce_int(
                flat.get("search_max_concurrent"), d("search_max_concurrent"), lo=1, hi=5
            ),
            search_show_progress=_coerce_bool(
                flat.get("search_show_progress"), d("search_show_progress")
            ),
        )

    @classmethod
    def _default(cls, name: str) -> Any:
        """Fallback for `from_mapping`: the dataclass field default is the
        single source of truth, so defaults are never written twice."""

        spec = cls.__dataclass_fields__[name]
        if spec.default is not MISSING:
            return spec.default
        return spec.default_factory()  # type: ignore[misc]

    # convenience predicates -------------------------------------------
    @property
    def is_openai_compatible(self) -> bool:
        return self.llm_provider == "openai_compatible"

    def has_llm_credentials(self) -> bool:
        return bool(self.llm_api_base and self.llm_api_key)
