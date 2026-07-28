"""Builder + filesystem store for swing_trade_plan."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.swing_trade_plan_builder import build_swing_trade_plan
from src.application.services.swing_trade_plan_store import (
    latest_plan_path,
    load_swing_trade_plan,
    plans_dir_from_journal_path,
    save_swing_trade_plan,
)
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup


def test_build_and_save_round_trip(tmp_path) -> None:
    setup = TradeSetup(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 28),
        action=SetupAction.WATCH,
        signal_score=70,
        signal_score_raw=70,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="test",
    )
    sizing = SimpleNamespace(
        entry_price=Decimal("6225"),
        stop_price=Decimal("6000"),
        target_price=Decimal("6500"),
        lots=12,
        risk_amount=Decimal("100000"),
    )
    plan = build_swing_trade_plan(
        ticker="bbca",
        as_of=date(2026, 7, 28),
        trade_setup=setup,
        setup_eval=SimpleNamespace(match=SimpleNamespace(value="MATCH")),
        setup_name="foreign-bounce",
        sizing=sizing,
        setup_sizing=None,
        capital=10_000_000,
        risk_pct=1.0,
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
        max_hold_days=10,
        with_market_context=False,
        with_technical_gate=False,
    )
    assert plan.is_complete
    assert plan.action_source == "screen_judgment"
    journal = tmp_path / "journals" / "accumulation.csv"
    journal.parent.mkdir(parents=True)
    plans_dir = plans_dir_from_journal_path(journal)
    path = save_swing_trade_plan(plan, plans_dir)
    assert path == latest_plan_path(plans_dir, "BBCA")
    loaded = load_swing_trade_plan(path)
    assert loaded.plan_id == plan.plan_id
    assert loaded.lots == 12
