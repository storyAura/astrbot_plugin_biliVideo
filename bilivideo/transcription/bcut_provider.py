"""必剪 (BCut) ASR provider.

Cleaned-up version of the original `BcutTranscriber` that emits typed
`TranscriptResult` objects and surfaces failures via `TranscriptionError`.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import requests

from ..core.exceptions import TranscriptionError
from ..core.logging import get_logger
from ..core.types import TranscriptResult, TranscriptSegment

logger = get_logger("BiliVideo/BCut")

API_BASE = "https://member.bilibili.com/x/bcut/rubick-interface"
ENDPOINT_CREATE = f"{API_BASE}/resource/create"
ENDPOINT_COMMIT = f"{API_BASE}/resource/create/complete"
ENDPOINT_TASK = f"{API_BASE}/task"
ENDPOINT_RESULT = f"{API_BASE}/task/result"

_HEADERS = {
    "User-Agent": "Bilibili/1.0.0 (https://www.bilibili.com)",
    "Content-Type": "application/json",
}

# Polling parameters
POLL_INTERVAL_SECONDS = 1.0
POLL_MAX_TRIES = 500


class BCutTranscriber:
    """Synchronous wrapper around 必剪 ASR.

    Bilibili exposes this for free; the API is HTTP+JSON with multipart
    upload to a presigned URL list. We deliberately stay synchronous so
    callers can run us via `loop.run_in_executor`.
    """

    def transcribe(
        self, file_path: str, cancel_event: threading.Event | None = None
    ) -> TranscriptResult:
        try:
            with requests.Session() as session:
                payload = self._upload(session, file_path)
                task_id = self._create_task(session, payload["download_url"])
                data = self._await_result(session, task_id, cancel_event)
        except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
            raise TranscriptionError(f"BCut ASR failed: {exc}") from exc

        result_json = json.loads(data["result"])
        segments: list[TranscriptSegment] = []
        full_pieces: list[str] = []
        for u in result_json.get("utterances", []):
            text = (u.get("transcript") or "").strip()
            if not text:
                continue
            start_ms = float(u.get("start_time", 0))
            end_ms = float(u.get("end_time", 0))
            segments.append(
                TranscriptSegment(
                    start=start_ms / 1000.0,
                    end=end_ms / 1000.0,
                    text=text,
                )
            )
            full_pieces.append(text)

        return TranscriptResult(
            language=result_json.get("language", "zh"),
            full_text=" ".join(full_pieces).strip(),
            segments=tuple(segments),
            raw=result_json,
        )

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _upload(self, session: requests.Session, file_path: str) -> dict[str, Any]:
        with open(file_path, "rb") as fp:
            data = fp.read()
        if not data:
            raise TranscriptionError("audio file is empty")

        meta = self._post_json(
            session,
            ENDPOINT_CREATE,
            {
                "type": 2,
                "name": "audio.mp3",
                "size": len(data),
                "ResourceFileType": "mp3",
                "model_id": "8",
            },
        )
        upload_urls = meta["upload_urls"]
        per_size = meta["per_size"]
        in_boss_key = meta["in_boss_key"]
        resource_id = meta["resource_id"]
        upload_id = meta["upload_id"]

        etags: list[str] = []
        for clip, url in enumerate(upload_urls):
            start = clip * per_size
            end = min((clip + 1) * per_size, len(data))
            resp = session.put(
                url,
                data=data[start:end],
                headers={"Content-Type": "application/octet-stream"},
                timeout=30,
            )
            resp.raise_for_status()
            etag = resp.headers.get("Etag", "").strip('"')
            etags.append(etag)

        commit = self._post_json(
            session,
            ENDPOINT_COMMIT,
            {
                "InBossKey": in_boss_key,
                "ResourceId": resource_id,
                "Etags": ",".join(etags),
                "UploadId": upload_id,
                "model_id": "8",
            },
        )
        return commit

    def _create_task(self, session: requests.Session, download_url: str) -> str:
        payload = self._post_json(
            session,
            ENDPOINT_TASK,
            {"resource": download_url, "model_id": "8"},
        )
        return payload["task_id"]

    def _await_result(
        self,
        session: requests.Session,
        task_id: str,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        for attempt in range(POLL_MAX_TRIES):
            if cancel_event is not None and cancel_event.is_set():
                raise TranscriptionError("BCut transcription cancelled")
            resp = session.get(
                ENDPOINT_RESULT,
                params={"model_id": 7, "task_id": task_id},
                headers=_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0:
                raise TranscriptionError(payload.get("message", "BCut query failed"))
            data = payload["data"]
            state = data.get("state")
            if state == 4:
                return data
            if state == 3:
                raise TranscriptionError(f"BCut task failed (state={state})")
            if attempt and attempt % 30 == 0:
                logger.info(f"BCut polling {attempt}/{POLL_MAX_TRIES}")
            time.sleep(POLL_INTERVAL_SECONDS)
        raise TranscriptionError("BCut task timed out")

    def _post_json(
        self, session: requests.Session, url: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        resp = session.post(url, data=json.dumps(body), headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise TranscriptionError(payload.get("message", "BCut request failed"))
        return payload["data"]
