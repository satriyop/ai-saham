"""
Compatibility facade for accumulation screen display helpers.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.screen_accum_formatters import (
    classify_pattern,
    fmt_score,
    format_value,
    notation_detail,
    notation_label,
)
from src.adapters.cli.screen_accum_guide_display import print_column_guide
from src.adapters.cli.screen_accum_multi_display import display_multi
from src.adapters.cli.screen_accum_single_display import display_results

__all__ = [
    "classify_pattern",
    "display_multi",
    "display_results",
    "fmt_score",
    "format_value",
    "notation_detail",
    "notation_label",
    "print_column_guide",
]
