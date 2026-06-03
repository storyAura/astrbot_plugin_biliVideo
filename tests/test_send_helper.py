"""yield_note_response forward-fallback tests.

A forward-node failure of ANY exception type must still deliver the already
rendered image/text components rather than crash the handler.
"""

from __future__ import annotations

from bilivideo.handlers import _send_helper


class _Cfg:
    enable_forward_message = True
    forward_bot_name = "bot"
    forward_bot_uin = "0"


class _Logger:
    def warning(self, *_a, **_k) -> None: ...


class _Services:
    config = _Cfg()
    logger = _Logger()


class _Event:
    def __init__(self) -> None:
        self.results: list = []

    def chain_result(self, payload):
        self.results.append(("chain", payload))
        return ("chain", payload)

    def plain_result(self, payload):
        self.results.append(("plain", payload))
        return ("plain", payload)


async def test_forward_value_error_still_yields_components(monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise ValueError("node 构造失败")  # NOT a RuntimeError

    monkeypatch.setattr(_send_helper, "build_video_forward_nodes", _boom)

    event = _Event()
    out = []
    async for resp in _send_helper.yield_note_response(
        _Services(), event, ["IMG_A", "IMG_B"], video_info=object()
    ):
        out.append(resp)

    # both components were delivered individually despite the forward crash
    assert ("chain", ["IMG_A"]) in event.results
    assert ("chain", ["IMG_B"]) in event.results
    assert len(out) == 2


async def test_text_fallback_when_forward_fails(monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise TypeError("Node signature drift")

    monkeypatch.setattr(_send_helper, "build_video_forward_nodes", _boom)

    event = _Event()
    out = []
    async for resp in _send_helper.yield_note_response(
        _Services(), event, "纯文本兜底", video_info=object()
    ):
        out.append(resp)

    assert event.results == [("plain", "纯文本兜底")]
    assert len(out) == 1
