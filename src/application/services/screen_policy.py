"""ScreenPolicy — per-scenario interpretation for ScreenAssessmentPipeline.

Layer: Application

Policy is data (not a Protocol): inspectable in tests, free of IO.
Fetch strategy (pre-built GateContext vs self-fetch) lives on RiskInputsBuilder,
not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskMode(str, Enum):
    """How risk results affect the screen outcome."""

    BLOCK = "block"
    """Risk participates in TradeSetup composition (BLOCKED_* actions)."""

    ANNOTATE = "annotate"
    """Risk is non-blocking context only; never filters the candidate list."""


@dataclass(frozen=True)
class ScreenPolicy:
    """Per-scenario assessment applicability and risk interpretation."""

    signal_applicable: bool
    trade_setup_applicable: bool
    risk_mode: RiskMode

    @staticmethod
    def accumulation() -> "ScreenPolicy":
        return ScreenPolicy(
            signal_applicable=True,
            trade_setup_applicable=True,
            risk_mode=RiskMode.BLOCK,
        )

    @staticmethod
    def pre_open() -> "ScreenPolicy":
        return ScreenPolicy(
            signal_applicable=False,
            trade_setup_applicable=False,
            risk_mode=RiskMode.ANNOTATE,
        )
