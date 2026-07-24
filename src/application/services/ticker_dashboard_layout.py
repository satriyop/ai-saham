"""
Panel layout policy for the ticker dashboard.

Layer: Application
"""

from __future__ import annotations

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
    if not brief:
        return FULL_PANEL_ORDER
    return tuple(key for key in FULL_PANEL_ORDER if key in BRIEF_PANEL_KEYS)


def should_render_panel(panel_key: str, *, brief: bool = False) -> bool:
    return panel_key in panel_keys_for_mode(brief=brief)
