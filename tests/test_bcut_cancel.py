"""Cooperative-cancellation tests for the BCut poll loop (hermetic, no network)."""

from __future__ import annotations

import threading

import pytest

from bilivideo.core.exceptions import TranscriptionError
from bilivideo.transcription import bcut_provider
from bilivideo.transcription.bcut_provider import BCutTranscriber


class _StubResponse:
    """Always reports 'still processing' (state != 3/4) so the loop would spin."""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"code": 0, "message": "ok", "data": {"state": 1}}


class _StubSession:
    """Counts polls so we can prove cancellation short-circuits the loop."""

    def __init__(self) -> None:
        self.calls = 0

    def get(self, url, *, params=None, headers=None, timeout=None) -> _StubResponse:
        self.calls += 1
        return _StubResponse()


def test_await_result_cancels_promptly(monkeypatch) -> None:
    # Arrange: never actually sleep, and pre-arm the cancel event.
    monkeypatch.setattr(bcut_provider.time, "sleep", lambda _seconds: None)
    session = _StubSession()
    cancel_event = threading.Event()
    cancel_event.set()

    # Act / Assert: raises immediately instead of exhausting POLL_MAX_TRIES.
    with pytest.raises(TranscriptionError, match="cancelled"):
        BCutTranscriber()._await_result(session, "task-id", cancel_event)

    assert session.calls == 0  # cancelled before the first network poll


def test_await_result_without_cancel_keeps_polling(monkeypatch) -> None:
    # Arrange: no sleeping; cap tries low so the "would loop forever" case ends.
    monkeypatch.setattr(bcut_provider.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(bcut_provider, "POLL_MAX_TRIES", 5)
    session = _StubSession()

    # Act / Assert: without cancellation it polls until it times out.
    with pytest.raises(TranscriptionError, match="timed out"):
        BCutTranscriber()._await_result(session, "task-id", None)

    assert session.calls == 5
