"""
Deprecated location for sector-macro panel.

ADR-054: sector macro is shown on ``saham screen accum TICKER`` (judgment desk).
See ``screen_accum_sector_macro_display.build_sector_macro_panel``.

This module remains as a thin re-export so any stale import fails loudly in tests
if still wired from plan swing — prefer deleting callers instead of using this.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.screen_accum_sector_macro_display import build_sector_macro_panel

__all__ = ["build_sector_macro_panel"]
