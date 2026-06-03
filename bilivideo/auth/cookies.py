"""Cookie persistence with atomic writes and restrictive permissions.

The previous implementation wrote `bili_cookies.json` directly with the
default umask, leaving the SESSDATA token world-readable on shared servers.
This module:
  * writes via `tempfile + os.replace` for crash-safety
  * `chmod 0600` after creation (best-effort on non-POSIX filesystems)
  * never raises into callers — all failures degrade gracefully to "no
    cookies", because this is non-critical state.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from ..core.logging import get_logger

logger = get_logger("BiliVideo/Cookies")

REQUIRED_COOKIE_KEY = "SESSDATA"
ALL_KNOWN_KEYS = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid", "buvid3")


class CookieJar:
    """File-backed cookie store with atomic write semantics."""

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / "bili_cookies.json"
        self._cookies: dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def save(self, cookies: Mapping[str, str]) -> None:
        clean = {k: str(v) for k, v in cookies.items() if v}
        if not clean.get(REQUIRED_COOKIE_KEY):
            logger.warning("Skipping save: missing SESSDATA")
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(clean)
        except OSError as exc:
            logger.warning(f"Atomic cookie write failed: {exc}")
            return
        self._cookies = clean
        logger.info("Bilibili cookies saved")

    def get(self) -> dict[str, str]:
        return dict(self._cookies)

    def is_logged_in(self) -> bool:
        return bool(self._cookies.get(REQUIRED_COOKIE_KEY))

    def clear(self) -> None:
        self._cookies = {}
        try:
            if self._path.exists():
                self._atomic_write({})
                self._path.unlink()
        except OSError as exc:
            logger.warning(f"Cookie file removal failed: {exc}")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"Cookie load failed ({self._path}): {exc}")
            return
        if not isinstance(data, dict):
            logger.warning("Cookie file format invalid; ignoring")
            return
        if data.get(REQUIRED_COOKIE_KEY):
            self._cookies = {k: str(v) for k, v in data.items() if v}
            logger.info("Bilibili cookies loaded")

    def _atomic_write(self, data: Mapping[str, str]) -> None:
        directory = self._path.parent
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=str(directory), prefix=".cookies.", suffix=".tmp"
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)
        try:
            temp_path.replace(self._path)
        except OSError:
            try:
                temp_path.unlink()
            finally:
                raise
        # tighten permissions; harmless on Windows where chmod is a stub
        with contextlib.suppress(OSError):
            os.chmod(self._path, 0o600)
