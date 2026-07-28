"""Build SwingTradePlan from a completed plan-swing workflow response.

Layer: Application
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.swing_trade_plan import (
    SWING_TRADE_PLAN_HORIZON,
    SwingTradePlan,
    compute_plan_id,
)


def build_swing_trade_plan(
    *,
    ticker: str,
    as_of,
    trade_setup: Any | None,
    setup_eval: Any | None,
    setup_name: str | None,
    sizing: Any | None,
    setup_sizing: Any | None,
    capital: int | float | Decimal | None,
    risk_pct: float | Decimal | None,
    take_profit_pct: Decimal | None,
    stop_loss_pct: Decimal | None,
    max_hold_days: int | None,
    with_market_context: bool,
    with_technical_gate: bool,
    latest_close: Decimal | None = None,
    created_at: datetime | None = None,
) -> SwingTradePlan:
    """Assemble a typed swing_trade_plan from plan workflow outputs."""
    chosen = setup_sizing or sizing
    entry = getattr(chosen, "entry_price", None) if chosen is not None else None
    stop = getattr(chosen, "stop_price", None) if chosen is not None else None
    target = getattr(chosen, "target_price", None) if chosen is not None else None
    lots = getattr(chosen, "lots", None) if chosen is not None else None
    risk_amount = getattr(chosen, "risk_amount", None) if chosen is not None else None

    if entry is None and latest_close is not None:
        entry = latest_close

    action = None
    action_source = "unavailable"
    if trade_setup is not None:
        action_obj = getattr(trade_setup, "action", None)
        action = getattr(action_obj, "value", action_obj)
        action = str(action) if action is not None else None
        # Default path inherits screen (S3); explicit flags recompute.
        if with_market_context or with_technical_gate:
            action_source = "plan_recomputed"
        else:
            action_source = "screen_judgment"

    setup_match = None
    if setup_eval is not None:
        match = getattr(setup_eval, "match", None)
        setup_match = getattr(match, "value", match)
        setup_match = str(setup_match) if setup_match is not None else None

    incomplete_reason = None
    if capital is None:
        incomplete_reason = "capital_not_provided"
    elif chosen is None or lots is None or (isinstance(lots, int) and lots <= 0):
        incomplete_reason = "sizing_unavailable"
    elif stop is None or target is None or entry is None:
        incomplete_reason = "geometry_incomplete"

    created = created_at or datetime.now(IDX_TIMEZONE)
    draft = {
        "ticker": ticker.upper(),
        "as_of": as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of),
        "horizon": SWING_TRADE_PLAN_HORIZON,
        "action": action,
        "action_source": action_source,
        "entry_price": str(entry) if entry is not None else None,
        "stop_price": str(stop) if stop is not None else None,
        "target_price": str(target) if target is not None else None,
        "lots": lots,
        "capital": str(capital) if capital is not None else None,
        "risk_pct": str(risk_pct) if risk_pct is not None else None,
        "setup_name": setup_name,
        "setup_match": setup_match,
        "max_hold_days": max_hold_days,
        "with_market_context": with_market_context,
        "with_technical_gate": with_technical_gate,
        "created_at": created.isoformat(),
        "incomplete_reason": incomplete_reason,
    }
    plan_id = compute_plan_id(draft)

    return SwingTradePlan(
        ticker=ticker.upper(),
        as_of=as_of if hasattr(as_of, "year") else created.date(),
        horizon=SWING_TRADE_PLAN_HORIZON,
        action=action,
        action_source=action_source,
        entry_price=Decimal(str(entry)) if entry is not None else None,
        stop_price=Decimal(str(stop)) if stop is not None else None,
        target_price=Decimal(str(target)) if target is not None else None,
        lots=int(lots) if lots is not None else None,
        capital=Decimal(str(capital)) if capital is not None else None,
        risk_pct=Decimal(str(risk_pct)) if risk_pct is not None else None,
        risk_amount=Decimal(str(risk_amount)) if risk_amount is not None else None,
        setup_name=setup_name,
        setup_match=setup_match,
        max_hold_days=max_hold_days,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        with_market_context=with_market_context,
        with_technical_gate=with_technical_gate,
        created_at=created,
        plan_id=plan_id,
        incomplete_reason=incomplete_reason,
    )
