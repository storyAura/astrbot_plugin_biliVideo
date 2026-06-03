"""YouTube cookie capture + persistence for yt-dlp.

YouTube (unlike Bilibili) has no QR/scan login that yt-dlp can drive, so the
only reliable credential is a cookies jar. To keep the UX in line with
``/B站登录`` — and crucially to avoid asking a VPS user to create a file on the
server — the bot captures the cookies **through chat** (the user pastes what
their browser exported) and persists them here, in the plugin data dir.

Accepts two paste shapes:
  * a Netscape ``cookies.txt`` (what "Get cookies.txt" browser extensions emit)
  * a simple ``name=value; name2=value2`` Cookie header string

Both are normalized to a Netscape file scoped to ``.youtube.com`` and written
atomically with ``chmod 0600`` (mirrors ``auth.cookies.CookieJar``).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from ..core.logging import get_logger

logger = get_logger("BiliVideo/YouTubeCookies")

_NETSCAPE_HEADER = "# Netscape HTTP Cookie File"


def normalize_youtube_cookies(raw: str) -> str | None:
    """Turn a pasted cookie blob into Netscape ``cookies.txt`` content.

    Returns ``None`` when nothing cookie-shaped can be parsed.
    """

    text = (raw or "").strip()
    if not text:
        return None
    if "\t" in text:
        return _from_netscape(text)
    if "=" in text:
        return _from_header(text)
    return None


def count_cookies(netscape: str) -> int:
    """Count data rows (7 tab-separated fields) in a Netscape jar."""

    return sum(1 for line in netscape.splitlines() if line.count("\t") >= 6)


def _from_netscape(text: str) -> str | None:
    data_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        # `#HttpOnly_` is a real data marker, not a comment.
        core = line[len("#HttpOnly_") :] if line.startswith("#HttpOnly_") else line
        if core.startswith("#"):
            continue
        if core.count("\t") >= 6:
            data_lines.append(line)
    if not data_lines:
        return None
    return _NETSCAPE_HEADER + "\n" + "\n".join(data_lines) + "\n"


def _from_header(text: str) -> str | None:
    pairs: list[tuple[str, str]] = []
    for chunk in text.replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        name = name.strip()
        if name:
            pairs.append((name, value.strip()))
    if not pairs:
        return None
    lines = [_NETSCAPE_HEADER]
    lines.extend(f".youtube.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}" for name, value in pairs)
    return "\n".join(lines) + "\n"


class YouTubeCookieStore:
    """File-backed YouTube cookies jar, written by the bot (not the user)."""

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / "youtube_cookies.txt"

    @property
    def path(self) -> str:
        return str(self._path)

    def has(self) -> bool:
        try:
            return self._path.exists() and self._path.stat().st_size > 0
        except OSError:
            return False

    def save(self, raw: str) -> int | None:
        """Normalize + persist a pasted cookie blob. Returns cookie count, or
        ``None`` if the paste was not cookie-shaped or the write failed."""

        netscape = normalize_youtube_cookies(raw)
        if not netscape:
            return None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(netscape)
        except OSError as exc:
            logger.warning(f"YouTube cookie write failed: {exc}")
            return None
        logger.info("YouTube cookies saved")
        return count_cookies(netscape)

    def clear(self) -> bool:
        try:
            if self._path.exists():
                self._path.unlink()
            return True
        except OSError as exc:
            logger.warning(f"YouTube cookie removal failed: {exc}")
            return False

    def _atomic_write(self, content: str) -> None:
        directory = self._path.parent
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=str(directory),
            prefix=".ytcookies.", suffix=".tmp",
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)
        try:
            temp_path.replace(self._path)
        except OSError:
            with contextlib.suppress(OSError):
                temp_path.unlink()
            raise
        with contextlib.suppress(OSError):
            os.chmod(self._path, 0o600)
