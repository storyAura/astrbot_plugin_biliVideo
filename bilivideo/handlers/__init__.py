"""Command + event handler implementations.

Each public handler accepts `(services, event)` and yields response chains.
The Star class in `main.py` simply forwards `@filter.command` invocations
to the matching handler.
"""

from .auto_detect import handle_auto_detect
from .help import handle_help
from .login import handle_login, handle_logout
from .model import handle_model
from .push_target import (
    handle_add_push_group,
    handle_add_push_user,
    handle_list_push,
    handle_remove_push,
)
from .status import handle_clear_cache, handle_status
from .subscription import (
    handle_check_updates,
    handle_list_subscriptions,
    handle_subscribe,
    handle_unsubscribe,
)
from .summary import handle_latest_video, handle_summary
from .toggle import handle_toggle_detect
from .youtube import handle_youtube_login, handle_youtube_logout

__all__ = [
    "handle_add_push_group",
    "handle_add_push_user",
    "handle_auto_detect",
    "handle_check_updates",
    "handle_clear_cache",
    "handle_help",
    "handle_latest_video",
    "handle_list_push",
    "handle_list_subscriptions",
    "handle_login",
    "handle_logout",
    "handle_model",
    "handle_remove_push",
    "handle_status",
    "handle_subscribe",
    "handle_summary",
    "handle_toggle_detect",
    "handle_unsubscribe",
    "handle_youtube_login",
    "handle_youtube_logout",
]
