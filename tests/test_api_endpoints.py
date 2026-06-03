"""API endpoint fallback tests."""

from __future__ import annotations

import pytest

from bilivideo.api import endpoints
from bilivideo.core.constants import ENDPOINT_SEARCH_TYPE, ENDPOINT_SEARCH_TYPE_WBI
from bilivideo.core.exceptions import BilibiliAPIError, NetworkError


class _StubClient:
    def __init__(self, responses: list[object]) -> None:
        self.cookies: dict[str, str] = {}
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    async def request_json(self, method: str, url: str, *, params=None, **kwargs):
        self.calls.append((url, dict(params or {})))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_uploader_info_api_error_returns_none(monkeypatch) -> None:
    async def _signed(params, *, cookies=None):
        return {**params, "w_rid": "x"}

    monkeypatch.setattr(endpoints, "sign_params", _signed)
    client = _StubClient([BilibiliAPIError(-401, "auth")])

    assert await endpoints.get_uploader_info(client, "123") is None


@pytest.mark.asyncio
async def test_latest_videos_api_error_returns_empty(monkeypatch) -> None:
    async def _signed(params, *, cookies=None):
        return {**params, "w_rid": "x"}

    monkeypatch.setattr(endpoints, "sign_params", _signed)
    client = _StubClient([BilibiliAPIError(-401, "auth")])

    assert await endpoints.get_latest_videos(client, "123") == []


@pytest.mark.asyncio
async def test_search_videos_skips_wbi_when_signing_unavailable(monkeypatch) -> None:
    async def _unsigned(params, *, cookies=None):
        return dict(params)

    monkeypatch.setattr(endpoints, "sign_params", _unsigned)
    client = _StubClient(
        [
            {
                "data": {
                    "result": [
                        {
                            "type": "video",
                            "bvid": "BV1xx411c7mD",
                            "title": "t",
                        }
                    ],
                    "numResults": 1,
                }
            }
        ]
    )

    result = await endpoints.search_videos(client, "keyword")

    assert result is not None
    assert len(result.results) == 1
    assert [url for url, _ in client.calls] == [ENDPOINT_SEARCH_TYPE]


@pytest.mark.asyncio
async def test_search_videos_falls_back_from_wbi_error(monkeypatch) -> None:
    async def _signed(params, *, cookies=None):
        return {**params, "w_rid": "x"}

    monkeypatch.setattr(endpoints, "sign_params", _signed)
    client = _StubClient(
        [
            NetworkError("wbi down"),
            {
                "data": {
                    "result": [
                        {
                            "type": "video",
                            "bvid": "BV1xx411c7mD",
                            "title": "legacy",
                        }
                    ],
                    "numResults": 1,
                }
            },
        ]
    )

    result = await endpoints.search_videos(client, "keyword")

    assert result is not None
    assert result.results[0].title == "legacy"
    assert [url for url, _ in client.calls] == [ENDPOINT_SEARCH_TYPE_WBI, ENDPOINT_SEARCH_TYPE]
