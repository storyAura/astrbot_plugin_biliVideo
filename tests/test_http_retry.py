"""HTTP client retry / error-mapping tests using a fake aiohttp session."""

from __future__ import annotations

import asyncio
import json

import aiohttp
import pytest

from bilivideo.api.client import BilibiliHTTPClient
from bilivideo.core.exceptions import BilibiliAPIError, NetworkError, RiskControlError


class _FakeResponse:
    def __init__(self, *, status: int, body: str = "") -> None:
        self.status = status
        self._body = body
        self.url = "http://x"

    async def text(self) -> str:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Minimal fake of aiohttp.ClientSession.

    Sequentially returns the responses from `responses`; once exhausted,
    raises `aiohttp.ClientError` to simulate a transient failure.
    """

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls = 0
        self.closed = False

    def request(self, method, url, *, params=None, json=None, headers=None):
        self.calls += 1
        if not self._responses:
            raise aiohttp.ClientError("no more fake responses")
        return self._responses.pop(0)

    def get(self, url, *, headers=None, allow_redirects=False):
        return self.request("GET", url, headers=headers)

    async def close(self) -> None:
        self.closed = True


def _payload(code: int, message: str = "ok", **extra) -> str:
    return json.dumps({"code": code, "message": message, **extra})


@pytest.mark.asyncio
async def test_success_first_try(monkeypatch) -> None:
    session = _FakeSession([_FakeResponse(status=200, body=_payload(0))])
    client = BilibiliHTTPClient()
    monkeypatch.setattr(client, "_ensure_session", _make_session_returner(session))

    out = await client.request_json("GET", "http://x")
    assert out["code"] == 0
    assert session.calls == 1


@pytest.mark.asyncio
async def test_retries_on_transient_error(monkeypatch) -> None:
    session = _FakeSession([_FakeResponse(status=500), _FakeResponse(status=200, body=_payload(0))])
    client = BilibiliHTTPClient()
    monkeypatch.setattr(client, "_ensure_session", _make_session_returner(session))
    # speed up backoff
    monkeypatch.setattr("bilivideo.api.client.HTTP_BACKOFF_BASE", 0.001)
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    out = await client.request_json("GET", "http://x")
    assert out["code"] == 0
    assert session.calls == 2


@pytest.mark.asyncio
async def test_fails_after_max_retries(monkeypatch) -> None:
    session = _FakeSession([_FakeResponse(status=500)] * 3)
    client = BilibiliHTTPClient()
    monkeypatch.setattr(client, "_ensure_session", _make_session_returner(session))
    monkeypatch.setattr("bilivideo.api.client.HTTP_BACKOFF_BASE", 0.001)
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    with pytest.raises(NetworkError):
        await client.request_json("GET", "http://x")
    assert session.calls == 3


@pytest.mark.asyncio
async def test_bilibili_code_412_raises_risk_control(monkeypatch) -> None:
    session = _FakeSession([_FakeResponse(status=200, body=_payload(-412, "风控"))])
    client = BilibiliHTTPClient()
    monkeypatch.setattr(client, "_ensure_session", _make_session_returner(session))

    with pytest.raises(RiskControlError):
        await client.request_json("GET", "http://x")


@pytest.mark.asyncio
async def test_bilibili_other_error_code_raises_api_error(monkeypatch) -> None:
    session = _FakeSession([_FakeResponse(status=200, body=_payload(-401, "auth"))])
    client = BilibiliHTTPClient()
    monkeypatch.setattr(client, "_ensure_session", _make_session_returner(session))

    with pytest.raises(BilibiliAPIError) as info:
        await client.request_json("GET", "http://x")
    assert info.value.code == -401


# ──────────────────────── helpers ────────────────────────


def _make_session_returner(session):
    async def _get():
        return session

    return _get


async def _noop_sleep(_seconds):
    return None
