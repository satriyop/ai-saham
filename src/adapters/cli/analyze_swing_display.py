"""
Display helpers for saham analyze swing commands.

Layer: Adapter

Compatibility facade: implementations now live in focused modules
(analyze_swing_formatters, analyze_swing_overview_display,
analyze_swing_evidence_display, analyze_swing_compare_display). This module
re-exports the public API that CLI command adapters and tests import.
"""

from __future__ import annotations

from src.adapters.cli.analyze_swing_compare_display import display_swing_compare
from src.adapters.cli.analyze_swing_evidence_display import (
    has_bandar_distribution,
    has_current_flow_confirmation,
    print_swing_output,
)
from src.adapters.cli.analyze_swing_formatters import (
    SwingDisplayConfig,
    _fmt_pct_compare,
    fmt_date,
    fmt_pct,
    flow_direction_label,
    foreign_flow_evidence_label,
    notation_detail,
    notation_label,
    sep,
    section_header,
    signal_label,
    style_bb,
    style_gate,
    style_risk,
    style_score,
    style_sentiment_call,
    style_setup_match,
    style_trend,
    style_winrate,
    swing_summary_parts,
)
from src.adapters.cli.analyze_swing_overview_display import (
    flow_trigger_blocked_text,
    format_failed_gates_summary,
    print_swing_rich_overview,
    setup_gates_group,
    swing_plan_text,
)

__all__ = [
    "SwingDisplayConfig",
    "display_swing_compare",
    "flow_direction_label",
    "flow_trigger_blocked_text",
    "fmt_date",
    "fmt_pct",
    "foreign_flow_evidence_label",
    "format_failed_gates_summary",
    "has_bandar_distribution",
    "has_current_flow_confirmation",
    "notation_detail",
    "notation_label",
    "print_swing_output",
    "print_swing_rich_overview",
    "sep",
    "section_header",
    "setup_gates_group",
    "signal_label",
    "style_bb",
    "style_gate",
    "style_risk",
    "style_score",
    "style_sentiment_call",
    "style_setup_match",
    "style_trend",
    "style_winrate",
    "swing_plan_text",
    "swing_summary_parts",
]
