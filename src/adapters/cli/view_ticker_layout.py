"""
Panel layout policy for the ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

# Full dashboard order. Keep stable for tests and JSON keys.
FULL_PANEL_ORDER: tuple[str, ...] = (
    "identity",
    "freshness",
    "valuation",
    "price_structure",
    "analyst",
    "earnings",
    "ownership",
    "bandar",
    "foreign_flow",
    "corp_actions",
    "insider",
    "seasonality",
    "iev",
    "sentiment",
    "profile",
    "candles",
)

# Brief mode: decision-relevant market facts only.
BRIEF_PANEL_KEYS: frozenset[str] = frozenset(
    {
        "identity",
        "freshness",
        "valuation",
        "price_structure",
        "earnings",
        "bandar",
        "foreign_flow",
    }
)


def panel_keys_for_mode(*, brief: bool = False) -> tuple[str, ...]:
    """Return ordered panel keys for full or brief dashboard mode."""
    if not brief:
        return FULL_PANEL_ORDER
    return tuple(key for key in FULL_PANEL_ORDER if key in BRIEF_PANEL_KEYS)


def should_render_panel(panel_key: str, *, brief: bool = False) -> bool:
    return panel_key in panel_keys_for_mode(brief=brief)
