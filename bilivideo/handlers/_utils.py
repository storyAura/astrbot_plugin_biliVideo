"""Shared helpers for command handlers."""

from __future__ import annotations


def parse_command_args(message: str) -> str:
    """Return everything after the command word, stripped.

    ``/订阅 123456`` -> ``123456``. Returns ``""`` when no argument is present.
    """

    if not message:
        return ""
    parts = message.strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""
