"""Access control, cooldown, and in-flight deduplication."""

from .control import is_allowed
from .cooldown import CooldownTracker
from .inflight import InflightDeduper
from .keyed_lock import KeyedLocks

__all__ = ["CooldownTracker", "InflightDeduper", "KeyedLocks", "is_allowed"]
