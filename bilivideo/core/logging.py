"""Tagged logger wrapper.

Keeps verbosity-controlled debug output ("dbg") separated from regular
info/warning/error so we don't pollute user-visible logs when debug mode is
disabled. Falls back to the stdlib logger when AstrBot's logger is missing
(useful for tests).
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from astrbot.api import logger as _astrbot_logger  # type: ignore[import]
except Exception:  # pragma: no cover - test environment
    _astrbot_logger = None  # type: ignore[assignment]


_FALLBACK = logging.getLogger("bilivideo")


class TaggedLogger:
    """Thin wrapper that prefixes a tag onto every log record."""

    __slots__ = ("_debug_enabled", "_tag")

    def __init__(self, tag: str, *, debug_enabled: bool = False) -> None:
        self._tag = tag
        self._debug_enabled = debug_enabled

    def set_debug(self, enabled: bool) -> None:
        self._debug_enabled = enabled

    def _emit(self, level: str, msg: str, *args: Any, **kwargs: Any) -> None:
        line = f"[{self._tag}] {msg}"
        target = _astrbot_logger or _FALLBACK
        method = getattr(target, level, None)
        if method is None:
            method = target.info  # type: ignore[union-attr]
        method(line, *args, **kwargs)

    # public API ---------------------------------------------------------
    def info(self, msg: str, *a: Any, **kw: Any) -> None:
        self._emit("info", msg, *a, **kw)

    def warning(self, msg: str, *a: Any, **kw: Any) -> None:
        self._emit("warning", msg, *a, **kw)

    def error(self, msg: str, *a: Any, **kw: Any) -> None:
        self._emit("error", msg, *a, **kw)

    def debug(self, msg: str, *a: Any, **kw: Any) -> None:
        """Debug logs only emit when debug mode is on; downgrade to info so
        AstrBot's default INFO-level logger surfaces them, mirroring the
        previous codebase's convention."""

        if not self._debug_enabled:
            return
        self._emit("info", f"DBG {msg}", *a, **kw)


def get_logger(tag: str, *, debug_enabled: bool = False) -> TaggedLogger:
    return TaggedLogger(tag, debug_enabled=debug_enabled)
