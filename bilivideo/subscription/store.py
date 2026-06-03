"""Atomic JSON store for subscription state.

Replaces the original implementation that wrote in place under a thread
lock. We now:
  * write to a sibling tempfile and `os.replace()` for crash-safety
  * fsync before rename so power-loss can't yield a half-written file
  * keep an in-memory cache to avoid repeated disk reads
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..core.logging import get_logger

logger = get_logger("BiliVideo/Store")


class JsonStore:
    """Simple async JSON store with atomic writes and an asyncio.Lock."""

    def __init__(self, path: str | Path, *, default: Mapping[str, Any]) -> None:
        self._path = Path(path)
        # Deep-copy the default so mutations don't bleed into a module-level
        # constant (the previous implementation suffered from shallow copy).
        self._default = copy.deepcopy(dict(default))
        self._data: dict[str, Any] = self._load()
        self._lock = asyncio.Lock()

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
        directory = self._path.parent
        directory.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False, dir=str(directory),
                prefix=f".{self._path.stem}.", suffix=".tmp",
            ) as tmp:
                json.dump(self._data, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = Path(tmp.name)
            try:
                temp_path.replace(self._path)
            except OSError:
                temp_path.unlink(missing_ok=True)
                raise
        except OSError as exc:
            logger.error(f"store persist failed: {exc}")

    # ------------------------------------------------------------------
    # async helpers
    # ------------------------------------------------------------------
    async def read(self) -> dict[str, Any]:
        async with self._lock:
            return json.loads(json.dumps(self._data))  # deep copy via json roundtrip

    async def mutate(self, mutator) -> None:
        """Run `mutator(data)` under the lock and persist atomically."""

        async with self._lock:
            mutator(self._data)
            await self._persist()
