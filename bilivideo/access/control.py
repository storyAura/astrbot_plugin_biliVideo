"""Group-level whitelist/blacklist enforcement."""

from __future__ import annotations

from ..core.config import PluginConfig


def is_allowed(origin: str, *, config: PluginConfig) -> bool:
    """Return True when the origin is allowed to use the plugin."""

    if not origin:
        return True
    group_list = config.group_list
    if not group_list:
        return True

    # Exact segment match: a bare substring / suffix check would let group id
    # "10000" match an unrelated origin ending in "...910000" (whitelist
    # bypass) or wrongly block it in blacklist mode.
    segments = origin.split(":")
    matches = any(gid in segments for gid in group_list)
    if config.access_mode == "whitelist":
        return matches
    if config.access_mode == "blacklist":
        return not matches
    return True
