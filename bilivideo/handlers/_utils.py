"""Shared helpers for command handlers."""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator, Callable
from typing import Any

from ..access.control import is_allowed

ACCESS_DENIED_MESSAGE = "⛔ 你没有权限使用此插件"

Handler = Callable[..., AsyncIterator[object]]


def require_access(handler: Handler) -> Handler:
    """Reject events whose origin fails `is_allowed` before running `handler`.

    Wraps `(services, event)` async-generator handlers; replaces the denial
    boilerplate that was previously copy-pasted at the top of each handler.
    """

    @functools.wraps(handler)
    async def wrapper(services: Any, event: Any, *args: Any, **kwargs: Any) -> AsyncIterator[object]:
        if not is_allowed(getattr(event, "unified_msg_origin", ""), config=services.config):
            yield event.plain_result(ACCESS_DENIED_MESSAGE)
            return
        async for item in handler(services, event, *args, **kwargs):
            yield item

    return wrapper


def parse_command_args(message: str) -> str:
    """Return everything after the command word, stripped.

    ``/订阅 123456`` -> ``123456``. Returns ``""`` when no argument is present.
    """

    if not message:
        return ""
    parts = message.strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""
