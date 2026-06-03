"""Color palettes used by the renderer.

Kept in a tiny module so designers can edit colors without touching the
HTML template logic.
"""

from __future__ import annotations

from typing import Final

# Card border-left + background pairs cycled through the chapter list.
CARD_COLORS: Final[tuple[tuple[str, str], ...]] = (
    ("#60a5fa", "rgba(96,165,250,.10)"),   # blue
    ("#34d399", "rgba(52,211,153,.10)"),    # green
    ("#a78bfa", "rgba(167,139,250,.10)"),   # purple
    ("#fb923c", "rgba(251,146,60,.10)"),    # orange
    ("#22d3ee", "rgba(34,211,238,.10)"),    # cyan
    ("#f472b6", "rgba(244,114,182,.10)"),   # pink
)


def card_color_for(index: int) -> tuple[str, str]:
    return CARD_COLORS[index % len(CARD_COLORS)]
