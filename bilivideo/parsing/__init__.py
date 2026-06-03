"""URL / message parsing utilities."""

from .message_router import (
    MessageContext,
    looks_like_quoted_message,
    parse_event,
    url_from_card,
    url_from_raw_payload,
)
from .triggers import BILIBILI_HINTS, DEFAULT_TRIGGER_KEYWORDS, TriggerSet
from .url_extractor import (
    detect_platform,
    extract_bvid,
    extract_long_url,
    extract_short_url,
    extract_uid,
    is_bilibili_domain,
    parse_cq_json,
    parse_json_card,
)

__all__ = [
    "BILIBILI_HINTS",
    "DEFAULT_TRIGGER_KEYWORDS",
    "MessageContext",
    "TriggerSet",
    "detect_platform",
    "extract_bvid",
    "extract_long_url",
    "extract_short_url",
    "extract_uid",
    "is_bilibili_domain",
    "looks_like_quoted_message",
    "parse_cq_json",
    "parse_event",
    "parse_json_card",
    "url_from_card",
    "url_from_raw_payload",
]
