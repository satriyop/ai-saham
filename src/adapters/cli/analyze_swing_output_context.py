"""
Display context for `saham analyze swing`'s full-output rendering.

Bundles the swing analysis workflow's verdict/evidence/diagnostics DTOs
(src/application/dto/swing_analysis.py) with display-only extras (position
sizing, plan window, display config, and which optional panels to render)
so print_swing_output() and its panel builders take one object instead of
30+ individual parameters.

Layer: Adapter

This module only carries data; it must not decide TradeSetup.action or any
other business outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from src.adapters.cli.analyze_swing_formatters import SwingDisplayConfig
from src.application.dto.swing_analysis import SwingDiagnostics, SwingEvidence, SwingVerdict


def default_swing_display_config() -> SwingDisplayConfig:
    # Rescaled 0-120 -> 0-100 (see ADR-039). Note: these literals already
    # didn't match swing_config.py's canonical defaults before the rescale
    # (a pre-existing drift, not introduced here) — converted proportionally
    # but not unified with swing_config.py, which is unrelated cleanup.
    return SwingDisplayConfig(
        enter_min_score=58.3,
        watch_min_score=41.7,
        coiled_spring_bb_pctile=0.2,
        coiled_spring_min_score=58.3,
        strong_min_score=66.7,
        strong_min_streak=3,
        building_min_score=50.0,
        building_min_streak=2,
        foreign_bounce_max_hold_days=10,
    )


@dataclass(frozen=True)
class SwingOutputDisplayOptions:
    """Which optional evidence panels to render."""

    include_strategy: bool
    include_sentiment: bool
    include_flow_detail: bool
    include_signal_detail: bool
    include_risk_detail: bool
    include_market_detail: bool
    with_technical_gate: bool = False
    sentiment_verbose: bool = False


@dataclass(frozen=True)
class SwingOutputDisplayContext:
    """Everything print_swing_output() and its panel builders need for one ticker."""

    ticker: str
    today: date
    strategy_name: str
    window: int
    verdict: SwingVerdict
    evidence: SwingEvidence
    diagnostics: SwingDiagnostics
    options: SwingOutputDisplayOptions
    config: SwingDisplayConfig = field(default_factory=default_swing_display_config)
    atr_value: "Decimal | None" = None
    sizing: Any = None
    setup_sizing: Any = None
    capital: "int | None" = None
