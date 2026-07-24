"""
Panel layout helpers for ticker dashboard display.

Re-exports application layout policy.

Layer: Adapter
"""

from src.application.services.ticker_dashboard_layout import (  # noqa: F401
    BRIEF_PANEL_KEYS,
    FULL_PANEL_ORDER,
    panel_keys_for_mode,
    should_render_panel,
)
