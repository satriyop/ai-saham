"""
Integration tests for AssessRiskUseCase with Phase B risk gates.

Verifies that:
- Structural gates (FundamentalGate, LiquidityGate) short-circuit before rule engine
- Execution gates (BandarGate) downgrade LOW_RISK after rule engine
- gate_triggered is set on the response when a gate fires
- No gates active (default) → behaviour unchanged
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.use_case.assess_risk_use_case import (
    AssessRiskRequest,
    AssessRiskUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.rules.risk_gate import GateContext

# ─── Shared helpers ───────────────────────────────────────────────────────────

_TODAY = date(2026, 6, 23)
_1T = 1_000_000_000_000
_5B = 5_000_000_000


class _MockRepo(MarketDataRepository):
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def get_candles(self, ticker: str, start_date=None, end_date=None) -> list[Candle]:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date:
            rows = [c for c in rows if c.date >= start_date]
        if end_date:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker, start_date, end_date):
        return bool(self.get_candles(ticker, start_date, end_date))

    def get_date_range(self, ticker):
        rows = self.get_candles(ticker)
        return (rows[0].date, rows[-1].date) if rows else None

    def list_tickers_with_candles_between(self, start_date, end_date):
        return []


def _flat_candles(ticker: str = "BBCA", count: int = 365, price: float = 5000.0) -> list[Candle]:
    """Flat-price candles with liquid volume (above IDR 5B/day threshold).

    volume=2_000_000: 5000 × 2_000_000 = 10B IDR/day (2× the 5B floor).
    """
    return [
        Candle(
            ticker=ticker,
            date=_TODAY - timedelta(days=count - i),
            open=Decimal(str(price)),
            high=Decimal(str(price)),
            low=Decimal(str(price)),
            close=Decimal(str(price)),
            volume=2_000_000,
        )
        for i in range(count)
    ]


def _make_use_case(
    structural_gates=None,
    execution_gates=None,
    candles=None,
) -> AssessRiskUseCase:
    repo = _MockRepo(candles or _flat_candles())
    return AssessRiskUseCase(
        repository=repo,
        structural_gates=structural_gates,
        execution_gates=execution_gates,
    )


def _ctx(
    piotroski: int | None = 7,
    market_cap: int = 2 * _1T,
    five_day: str | None = "Big Acc",
) -> GateContext:
    return GateContext(
        ticker="BBCA",
        snapshot_date=_TODAY,
        piotroski_f_score=piotroski,
        market_cap_idr=market_cap,
        five_day_accdist=five_day,
    )


# ─── No gates — baseline unchanged ───────────────────────────────────────────


def test_no_gates_returns_technical_assessment():
    uc = _make_use_case()
    req = AssessRiskRequest(ticker="BBCA")
    resp = uc.execute(req)
    assert resp.gate_triggered is None
    assert resp.assessment is not None


def test_gates_inactive_when_no_gate_context():
    """Gates configured but no gate_context → technical result only."""
    uc = _make_use_case(structural_gates=[FundamentalGate()])
    req = AssessRiskRequest(ticker="BBCA", gate_context=None)
    resp = uc.execute(req)
    assert resp.gate_triggered is None


# ─── FundamentalGate integration ──────────────────────────────────────────────


def test_fundamental_gate_short_circuits_on_distress():
    uc = _make_use_case(structural_gates=[FundamentalGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(piotroski=2),
    )
    resp = uc.execute(req)
    assert resp.assessment.gate_triggered is not None
    assert resp.gate_triggered == "FundamentalGate"
    assert "F-score" in resp.assessment.rationale[0]


def test_fundamental_gate_passes_healthy_company():
    uc = _make_use_case(structural_gates=[FundamentalGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(piotroski=7),
    )
    resp = uc.execute(req)
    assert resp.gate_triggered is None


def test_fundamental_gate_passes_when_no_fundamental_data():
    uc = _make_use_case(structural_gates=[FundamentalGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(piotroski=None),
    )
    resp = uc.execute(req)
    assert resp.gate_triggered is None


# ─── LiquidityGate integration ────────────────────────────────────────────────


def test_liquidity_gate_fires_on_third_liner():
    uc = _make_use_case(structural_gates=[LiquidityGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(market_cap=500_000_000_000),  # 500B < 1T
    )
    resp = uc.execute(req)
    assert resp.assessment.gate_triggered is not None
    assert resp.gate_triggered == "LiquidityGate"


def test_liquidity_gate_fires_on_illiquid_candles():
    """Gate uses candles from repository when not provided in context."""
    illiquid_candles = [
        Candle(
            ticker="BBCA",
            date=_TODAY - timedelta(days=i),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=1_000,  # 100 × 1_000 = 100_000 IDR/day — far below 5B
        )
        for i in range(365)
    ]
    uc = _make_use_case(
        structural_gates=[LiquidityGate(liquidity_floor_idr=_5B)],
        candles=illiquid_candles,
    )
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=GateContext(
            ticker="BBCA",
            snapshot_date=_TODAY,
            market_cap_idr=2 * _1T,  # large cap — passes cap check
        ),
    )
    resp = uc.execute(req)
    assert resp.assessment.gate_triggered is not None
    assert resp.gate_triggered == "LiquidityGate"


def test_liquidity_gate_passes_liquid_large_cap():
    uc = _make_use_case(structural_gates=[LiquidityGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(market_cap=50 * _1T),
    )
    resp = uc.execute(req)
    assert resp.gate_triggered is None


# ─── BandarGate integration ───────────────────────────────────────────────────


def test_bandar_gate_fires_on_distribution():
    """BandarGate fires unconditionally on distribution label."""
    uc = _make_use_case(execution_gates=[BandarGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(
            five_day="Big Dist",
        ),
    )
    resp = uc.execute(req)
    assert resp.gate_triggered == "BandarGate"
    assert resp.assessment.gate_is_structural is False


def test_bandar_gate_does_not_fire_when_accumulating():
    uc = _make_use_case(execution_gates=[BandarGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(five_day="Big Acc"),
    )
    resp = uc.execute(req)
    assert resp.gate_triggered is None


# ─── Gate ordering: structural before execution ───────────────────────────────


def test_structural_gate_fires_before_execution_gate():
    """When FundamentalGate fires, verdict short-circuits; BandarGate is not_evaluated."""
    uc = _make_use_case(
        structural_gates=[FundamentalGate()],
        execution_gates=[BandarGate()],
    )
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(piotroski=1, five_day="Big Dist"),
    )
    resp = uc.execute(req)
    assert resp.gate_triggered == "FundamentalGate"
    assert resp.assessment.risk_level_name == "BLOCKED"
    by_gate = {row.gate: row for row in resp.gate_evaluations}
    assert by_gate["FundamentalGate"].outcome == "triggered"
    assert by_gate["BandarGate"].outcome == "not_evaluated"
    assert by_gate["BandarGate"].evaluated is False
    assert resp.gate_context_completeness is not None
    assert resp.gate_context_completeness.missingness["piotroski_f_score"] is False


# ─── Gate rationale preservation ──────────────────────────────────────────────


def test_structural_gate_preserves_gate_rationale():
    """Structural gate must surface the gate reason."""
    uc = _make_use_case(structural_gates=[FundamentalGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(piotroski=1),  # triggers FundamentalGate (F-score ≤ 3)
    )
    resp = uc.execute(req)
    assert resp.assessment.gate_triggered == "FundamentalGate"
    assert resp.assessment.risk_level_name == "BLOCKED"
    assert len(resp.assessment.rationale) >= 1
    assert "Piotroski" in resp.assessment.rationale[0] or "F-score" in resp.assessment.rationale[0]


def test_c2_records_skipped_outcome_when_fundamental_data_missing():
    uc = _make_use_case(structural_gates=[FundamentalGate()])
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(piotroski=None),
    )
    resp = uc.execute(req)
    assert resp.gate_triggered is None
    assert len(resp.gate_evaluations) == 1
    assert resp.gate_evaluations[0].outcome == "skipped"
    assert resp.gate_context_completeness is not None
    assert resp.gate_context_completeness.missingness["piotroski_f_score"] is True


def test_c2_all_gates_pass_records_pass_outcomes():
    uc = _make_use_case(
        structural_gates=[FundamentalGate()],
        execution_gates=[BandarGate()],
    )
    req = AssessRiskRequest(
        ticker="BBCA",
        gate_context=_ctx(piotroski=7, five_day="Big Acc"),
    )
    resp = uc.execute(req)
    assert resp.gate_triggered is None
    assert [row.outcome for row in resp.gate_evaluations] == ["pass", "pass"]
