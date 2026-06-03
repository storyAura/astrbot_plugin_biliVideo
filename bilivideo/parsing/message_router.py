"""Inspect `AstrMessageEvent` objects to extract Bilibili-relevant pieces.

The previous `on_all_message` handler was ~300 lines of nested branching
that mixed component traversal with URL extraction and trigger detection.
This module isolates the *parsing* concerns:

  * Walk the framework's component list to surface text content.
  * Detect reply/quote semantics so callers can decide policy.
  * Provide a single `MessageContext` object that downstream code uses.

Decisions about whether to act on a context (e.g. requiring trigger
keywords) live in `bilivideo.handlers.auto_detect`, not here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .url_extractor import find_qqdoc_url, parse_cq_json, parse_json_card

# OneBot/Onebot-v11 component type names we care about.
_REPLY_TYPES = {"reply", "quote"}
_AT_TYPES = {"at"}
_TEXT_TYPES = {"text", "plain"}


@dataclass(slots=True)
class MessageContext:
    """Snapshot of an inbound message after framework normalization."""

    plain_text: str = ""           # text the user actually typed (excluding reply)
    raw_message: str = ""          # framework-level string with CQ codes intact
    is_reply: bool = False         # leading component is reply/quote
    has_at: bool = False
    json_card_text: str = ""       # serialized JSON-card seen in components
    raw_payload: object | None = None  # framework's raw_message attribute


def parse_event(event: object) -> MessageContext:
    """Extract a `MessageContext` from any framework event.

    We treat `event` loosely so unit tests can pass plain dataclasses.
    """

    plain_pieces: list[str] = []
    is_reply = False
    has_at = False
    json_card_text = ""
    raw_payload: object | None = None

    text_msg = getattr(event, "message_str", "") or ""
    message_obj = getattr(event, "message_obj", None)
    if message_obj is not None:
        raw_payload = getattr(message_obj, "raw_message", None)

    raw_msg_str = ""
    if raw_payload is not None:
        raw_msg_str = str(raw_payload)

    components = []
    if message_obj is not None:
        components = list(getattr(message_obj, "message", []) or [])

    for idx, comp in enumerate(components):
        comp_type = (getattr(comp, "type", "") or "").lower()
        comp_name = type(comp).__name__.lower()

        if idx == 0 and (comp_type in _REPLY_TYPES or "reply" in comp_name or "quote" in comp_name):
            is_reply = True
            continue

        if comp_type in _AT_TYPES:
            has_at = True
            qq = (getattr(comp, "data", None) or {})
            qq_value = qq.get("qq", "") if isinstance(qq, dict) else ""
            plain_pieces.append(f"@{qq_value or 'someone'}")
            continue

        if comp_type in _TEXT_TYPES or hasattr(comp, "text"):
            text_value = getattr(comp, "text", None)
            if isinstance(text_value, str) and text_value:
                plain_pieces.append(text_value)
                continue

        if comp_type == "json" or "json" in comp_name:
            comp_str = str(comp)
            if comp_str:
                json_card_text = comp_str
            continue

    plain_text = " ".join(p for p in plain_pieces if p).strip()
    if not plain_text and not is_reply:
        plain_text = text_msg

    return MessageContext(
        plain_text=plain_text,
        raw_message=raw_msg_str or text_msg,
        is_reply=is_reply,
        has_at=has_at,
        json_card_text=json_card_text,
        raw_payload=raw_payload,
    )


def looks_like_quoted_message(raw_message: str, plain_text: str) -> bool:
    """Heuristic: any of these markers means the message is a quote/reply."""

    return (
        "[CQ:reply" in (raw_message or "")
        or "[CQ:reply" in (plain_text or "")
        or "[引用消息]" in (plain_text or "")
    )


def url_from_card(text: str) -> str | None:
    """Try CQ-json -> JSON parse -> regex extraction in order."""

    return parse_cq_json(text) or parse_json_card(text)


def url_from_raw_payload(raw: object) -> str | None:
    """Look inside `raw_message` (dict/list/str) for a JSON-card URL."""

    if raw is None:
        return None
    if isinstance(raw, dict):
        url = find_qqdoc_url(raw)
        if url:
            return url
        if raw.get("type") == "json":
            inner = raw.get("data")
            if isinstance(inner, dict):
                value = inner.get("data")
                if isinstance(value, str):
                    return parse_json_card(value)
            if isinstance(inner, str):
                return parse_json_card(inner)
        return None
    if isinstance(raw, list):
        for seg in raw:
            url = url_from_raw_payload(seg)
            if url:
                return url
        return None
    if isinstance(raw, str):
        return parse_cq_json(raw) or parse_json_card(raw)
    return None
