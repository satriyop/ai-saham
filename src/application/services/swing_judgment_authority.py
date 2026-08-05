"""Authoritative TradeSetup Action for plan vs screen (ADR-054 S3, ADR-067 §3).

Screen-composed ``AccumulationCandidate.trade_setup`` is the operator judgment
owner. Plan never recomputes Action — it carries the screen verdict forward
verbatim, and only composes a TradeSetup of its own when screen produced none
(a ticker that was never screened has no verdict to inherit).

Layer: Application
Pure: no IO, no engines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.value_objects.trade_setup import TradeSetup

SCREEN_JUDGMENT_WARNING = "Action from screen judgment (ADR-054 S3)"


def resolve_authoritative_trade_setup(
    candidate: Any | None,
    *,
    plan_recomputed: "TradeSetup | None",
) -> tuple["TradeSetup | None", str | None]:
    """Pick authoritative TradeSetup for plan verdict.

    Returns ``(setup, optional_warning)``.

    Rules:
    1. Screen ``candidate.trade_setup`` present → screen, always.
    2. No screen setup → fall back to ``plan_recomputed``.

    There is deliberately no flag that lets plan override rule 1: ADR-067 §3
    retired plan-side judgment entirely.
    """
    screen_setup = getattr(candidate, "trade_setup", None) if candidate is not None else None

    if screen_setup is not None:
        return screen_setup, SCREEN_JUDGMENT_WARNING

    return plan_recomputed, None
