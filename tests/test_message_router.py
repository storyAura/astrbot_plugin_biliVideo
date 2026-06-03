"""Message-routing helper tests using simple mocks."""

from __future__ import annotations

from dataclasses import dataclass, field

from bilivideo.parsing.message_router import (
    looks_like_quoted_message,
    parse_event,
    url_from_card,
)

# ──────────────────────── stub event/component types ───────────────


@dataclass
class _StubComponent:
    type: str = "text"
    text: str = ""
    data: dict | None = None


@dataclass
class _StubMessageObj:
    message: list = field(default_factory=list)
    raw_message: str | dict | None = None


@dataclass
class _StubEvent:
    message_str: str = ""
    message_obj: _StubMessageObj | None = None


# ──────────────────────── tests ────────────────────────────────────


class TestLooksLikeQuotedMessage:
    def test_cq_reply(self) -> None:
        assert looks_like_quoted_message("[CQ:reply,id=1]hello", "")

    def test_chinese_marker(self) -> None:
        assert looks_like_quoted_message("", "[引用消息] foo")

    def test_clean_message(self) -> None:
        assert not looks_like_quoted_message("hi", "hi")


class TestParseEvent:
    def test_plain_text_only(self) -> None:
        msg_obj = _StubMessageObj(message=[_StubComponent(text="看看 BV1xx")])
        event = _StubEvent(message_str="看看 BV1xx", message_obj=msg_obj)
        ctx = parse_event(event)
        assert "BV1xx" in ctx.plain_text
        assert not ctx.is_reply

    def test_reply_skipped(self) -> None:
        msg_obj = _StubMessageObj(
            message=[
                _StubComponent(type="reply"),
                _StubComponent(text="总结一下"),
            ]
        )
        event = _StubEvent(message_str="", message_obj=msg_obj)
        ctx = parse_event(event)
        assert ctx.is_reply
        assert ctx.plain_text == "总结一下"

    def test_at_component_collected(self) -> None:
        msg_obj = _StubMessageObj(
            message=[
                _StubComponent(type="at", data={"qq": "1234"}),
                _StubComponent(text="hi"),
            ]
        )
        event = _StubEvent(message_obj=msg_obj)
        ctx = parse_event(event)
        assert ctx.has_at
        assert "@1234" in ctx.plain_text


def test_url_from_card_handles_qqdocurl() -> None:
    text = '{"meta":{"x":{"qqdocurl":"https://b23.tv/abc"}}}'
    assert url_from_card(text) == "https://b23.tv/abc"
