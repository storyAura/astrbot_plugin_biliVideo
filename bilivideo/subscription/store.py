"""Atomic JSON store for subscription state.

Replaces the original implementation that wrote in place under a thread
lock. We now:
  * write to a sibling tempfile and `os.replace()` for crash-safety
  * fsync before rename so power-loss can't yield a half-written file
  * keep an in-memory cache to avoid repeated disk reads
  * run the blocking write in a worker thread; on failure the in-memory
    state is rolled back and the error propagates to the caller
  * guard renames with a write sequence so a write orphaned by task
    cancellation can never clobber a newer write
  * support `close()` so a stale plugin instance (hot-reload) can't keep
    dumping its old snapshot over the replacement instance's data
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..core.logging import get_logger

logger = get_logger("BiliVideo/Store")


class StoreClosedError(OSError):
    """Mutation attempted after `close()` — e.g. an in-flight handler from a
    hot-reloaded (old) plugin instance trying to write through its stale store."""


class JsonStore:
    """Simple async JSON store with atomic writes and an asyncio.Lock."""

    def __init__(self, path: str | Path, *, default: Mapping[str, Any]) -> None:
        self._path = Path(path)
        # Deep-copy the default so mutations don't bleed into a module-level
        # constant (the previous implementation suffered from shallow copy).
        self._default = copy.deepcopy(dict(default))
        self._data: dict[str, Any] = self._load()
        self._lock = asyncio.Lock()
        self._write_lock = threading.Lock()
        self._write_seq = 0  # issued on the event-loop thread only
        self._applied_seq = 0  # guarded by _write_lock
        self._closed = False

    def close(self) -> None:
        """Refuse all further mutations (reads stay allowed)."""

        self._closed = True

    # ------------------------------------------------------------------
    # disk IO
    # ------------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return copy.deepcopy(self._default)
        try:
            with self._path.open("r", encoding="utf-8") as fp:
                value = json.load(fp)
                if isinstance(value, dict):
                    return value
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"store load failed ({self._path}): {exc}")
        return copy.deepcopy(self._default)

    async def _persist(self) -> None:
        # Serialize on the loop thread (the lock guards `_data`), then hand the
        # blocking write+fsync+rename to a worker so the event loop never stalls.
        payload = json.dumps(self._data, ensure_ascii=False, indent=2)
        self._write_seq += 1
        write = asyncio.ensure_future(
            asyncio.to_thread(self._write_atomic, payload, self._write_seq)
        )
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            # The worker thread keeps running after cancellation; surface a
            # late failure in the log instead of losing it silently.
            write.add_done_callback(self._log_late_write_failure)
            raise
        except OSError as exc:
            logger.error(f"store persist failed ({self._path}): {exc}")
            raise

    def _log_late_write_failure(self, write: asyncio.Future) -> None:
        if write.cancelled():
            return
        exc = write.exception()
        if exc is not None:
            logger.error(f"orphaned store write failed ({self._path}): {exc}")

    def _write_atomic(self, payload: str, seq: int) -> None:
        directory = self._path.parent
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=str(directory),
            prefix=f".{self._path.stem}.", suffix=".tmp",
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)
        try:
            with self._write_lock:
                if seq <= self._applied_seq:
                    # A newer write already replaced the file; discarding this
                    # stale (typically cancelled-and-orphaned) one keeps it
                    # from clobbering fresher data.
                    temp_path.unlink(missing_ok=True)
                    return
                temp_path.replace(self._path)
                self._applied_seq = seq
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------
    # async helpers
    # ------------------------------------------------------------------
    async def read(self) -> dict[str, Any]:
        async with self._lock:
            return json.loads(json.dumps(self._data))  # deep copy via json roundtrip

    async def mutate(self, mutator) -> None:
        """Run `mutator(data)` under the lock and persist atomically.

        Rollback rules:
          * the mutator or the disk write fails → memory is rolled back to the
            pre-call snapshot and the error propagates, so memory never
            silently diverges from what a restart would reload;
          * the calling task is cancelled mid-write → the mutation is KEPT:
            the worker thread can't be interrupted and normally completes, so
            keeping it matches the disk, and the sequence guard in
            `_write_atomic` stops the orphaned write from clobbering a newer one.
        """

        async with self._lock:
            if self._closed:
                raise StoreClosedError(f"store {self._path} is closed")
            snapshot = copy.deepcopy(self._data)
            try:
                mutator(self._data)
                await self._persist()
            except asyncio.CancelledError:
                raise
            except BaseException:
                self._data = snapshot
                raise
