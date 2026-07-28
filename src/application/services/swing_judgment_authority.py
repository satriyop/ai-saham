"""Authoritative TradeSetup Action for plan vs screen (ADR-054 S3).

Screen-composed ``AccumulationCandidate.trade_setup`` is the operator judgment
owner. Plan may recompute Action only when explicit re-judge flags are set.

Layer: Application
Pure: no IO, no engines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.value_objects.trade_setup import TradeSetup

SCREEN_JUDGMENT_WARNING = "Action from screen judgment (ADR-054 S3)"


def allow_action_recompute(
    *,
    with_market_context: bool,
    with_technical_gate: bool,
) -> bool:
    """True when plan is allowed to replace screen TradeSetup.action."""
    return bool(with_market_context or with_technical_gate)


def resolve_authoritative_trade_setup(
    candidate: Any | None,
    *,
    plan_recomputed: "TradeSetup | None",
    allow_recompute: bool,
) -> tuple["TradeSetup | None", str | None]:
    """Pick authoritative TradeSetup for plan verdict.

    Returns ``(setup, optional_warning)``.

    Rules:
    1. Screen ``candidate.trade_setup`` present and not allow_recompute → screen.
    2. allow_recompute → plan_recomputed (even if None).
    3. No screen setup → fall back to plan_recomputed.
    """
    screen_setup = getattr(candidate, "trade_setup", None) if candidate is not None else None

    if allow_recompute:
        return plan_recomputed, None

    if screen_setup is not None:
        return screen_setup, SCREEN_JUDGMENT_WARNING

    return plan_recomputed, None
