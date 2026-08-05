"""AssessRiskGateEvaluator aggregates unevaluable gates onto the assessment.

A gate that ran without usable input asserted nothing. The assessment must say
so instead of reporting "all gates passed", and the count must be readable
without parsing prose.

Layer: Application
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
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.risk_gate import GateContext

_TODAY = date(2026, 6, 23)
_1T = 1_000_000_000_000


class _Repo(MarketDataRepository):
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


def _candles(count: int = 365, price: float = 5000.0) -> list[Candle]:
    return [
        Candle(
            ticker="BBCA",
            date=_TODAY - timedelta(days=count - i),
            open=Decimal(str(price)),
            high=Decimal(str(price)),
            low=Decimal(str(price)),
            close=Decimal(str(price)),
            volume=2_000_000,
        )
        for i in range(count)
    ]


def _use_case(structural=None, execution=None) -> AssessRiskUseCase:
    return AssessRiskUseCase(
        repository=_Repo(_candles()),
        structural_gates=structural,
        execution_gates=execution,
    )


def _ctx(**overrides) -> GateContext:
    base = {
        "piotroski_f_score": 7,
        "market_cap_idr": 2 * _1T,
        "free_float_pct": 40.0,
        "five_day_accdist": "Big Acc",
    }
    base.update(overrides)
    return GateContext(ticker="BBCA", snapshot_date=_TODAY, **base)


def test_fully_evaluated_gates_report_no_unknowns():
    uc = _use_case(structural=[FundamentalGate(), FreeFloatGate()], execution=[BandarGate()])
    resp = uc.execute(AssessRiskRequest(ticker="BBCA", gate_context=_ctx()))

    assert resp.assessment.unevaluable_gates == ()
    assert resp.assessment.unevaluable_gate_count == 0
    assert resp.assessment.rationale == ("all gates passed",)


def test_unevaluable_gates_are_named_in_evaluation_order():
    uc = _use_case(structural=[FundamentalGate(), FreeFloatGate()], execution=[BandarGate()])
    resp = uc.execute(
        AssessRiskRequest(
            ticker="BBCA",
            gate_context=_ctx(piotroski_f_score=None, five_day_accdist=None),
        )
    )

    assert resp.assessment.unevaluable_gates == ("FundamentalGate", "BandarGate")
    assert resp.assessment.unevaluable_gate_count == 2
    # No gate fired, so nothing blocks — only the explanation changes.
    assert resp.gate_triggered is None
    assert resp.risk_level == "open"


def test_rationale_never_claims_all_gates_passed_when_one_was_unevaluable():
    uc = _use_case(structural=[FundamentalGate()])
    resp = uc.execute(AssessRiskRequest(ticker="BBCA", gate_context=_ctx(piotroski_f_score=None)))

    rationale = resp.assessment.rationale[0]
    assert "all gates passed" not in rationale
    assert "1 gate unevaluable" in rationale
    assert "FundamentalGate" in rationale


def test_unknown_count_survives_a_blocking_gate():
    """A real block still records what the other gates could not check."""
    uc = _use_case(structural=[FundamentalGate(), FreeFloatGate()])
    resp = uc.execute(
        AssessRiskRequest(
            ticker="BBCA",
            gate_context=_ctx(piotroski_f_score=None, free_float_pct=2.0),
        )
    )

    assert resp.gate_triggered == "FreeFloatGate"
    assert resp.assessment.unevaluable_gates == ("FundamentalGate",)


def test_gates_that_never_ran_are_not_counted_as_unevaluable():
    """A short-circuited gate is `not_evaluated`, not `unevaluable`."""
    uc = _use_case(structural=[FundamentalGate(), FreeFloatGate()], execution=[BandarGate()])
    resp = uc.execute(
        AssessRiskRequest(
            ticker="BBCA",
            gate_context=_ctx(piotroski_f_score=1, five_day_accdist=None),
        )
    )

    assert resp.gate_triggered == "FundamentalGate"
    outcomes = {row.gate: row.outcome for row in resp.gate_evaluations}
    assert outcomes["BandarGate"] == "not_evaluated"
    assert resp.assessment.unevaluable_gates == ()


def test_unevaluable_gates_reach_the_persisted_payload():
    uc = _use_case(structural=[FundamentalGate()])
    resp = uc.execute(AssessRiskRequest(ticker="BBCA", gate_context=_ctx(piotroski_f_score=None)))

    payload = resp.assessment.to_dict()
    assert payload["unevaluable_gates"] == ["FundamentalGate"]
