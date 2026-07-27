from datetime import date
from decimal import Decimal

from src.application.use_case.swing_backtest_use_case import SwingBacktestTrade
from src.domain.value_objects.setup_evaluation import SetupGate


class ObservationFixture:
    def __init__(
        self,
        *,
        forward_return_pct: float,
        setup_match: str = "NO_MATCH",
        signal_score: int = 40,
        risk_status: str | None = None,
    ) -> None:
        self.forward_return_pct = forward_return_pct
        self.setup_match = setup_match
        self.signal_score = signal_score
        self.signal_strength = "WEAK"
        self.signal_breakdown = (("foreign_flow_quality", float(signal_score)),)
        self.setup_gates = (SetupGate("vwap_discount", False, "1", ">= 3"),)
        self.risk_status = risk_status
        self.risk_gate = None
        self.trade_setup_action = "WATCH"
        self.regime = None


def make_trade(
    *,
    ticker: str,
    net_return_pct: float,
    pnl: str,
    signal_strength: str | None = "STRONG",
    signal_score: int | None = 72,
    risk_status: str | None = "OPEN",
    risk_gate: str | None = None,
    regime: str | None = "RISK_ON",
) -> SwingBacktestTrade:
    return SwingBacktestTrade(
        ticker=ticker,
        entry_date=date(2026, 1, 1),
        exit_date=date(2026, 1, 2),
        entry_price=Decimal("100"),
        exit_price=Decimal("105"),
        lots=1,
        shares=100,
        entry_value=Decimal("10000"),
        exit_value=Decimal("10500"),
        gross_return_pct=5.0,
        net_return_pct=net_return_pct,
        pnl=Decimal(pnl),
        holding_days=1,
        exit_reason="target" if net_return_pct > 0 else "stop",
        accum_score=80.0,
        flow_pct=10.0,
        vwap_disc_pct=5.0,
        rsi=50.0,
        regime=regime,
        setup_match="MATCH",
        setup_gates=(
            SetupGate("accum_score", True, "80", ">= 70"),
            SetupGate("vwap_discount", net_return_pct > 0, "5", ">= 3"),
        ),
        trade_setup_action="ENTER",
        signal_score=signal_score,
        signal_strength=signal_strength,
        signal_entry_quality="ENTER",
        signal_breakdown=(
            ("bandar_intensity", 75.0),
            ("foreign_flow_quality", 82.0),
        ),
        risk_status=risk_status,
        risk_gate=risk_gate,
    )
