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

    matches = any(f":{gid}" in origin or origin.endswith(gid) for gid in group_list)
    if config.access_mode == "whitelist":
        return matches
    if config.access_mode == "blacklist":
        return not matches
    return True
