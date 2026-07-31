"""
Point-in-time cutoff (`as_of_date`) tests for the risk gate evaluation path.

`AssessRiskRequest.as_of_date` is the sole cutoff authority for the risk
path: None means "live" (latest cached data); a value is a hard inclusive
cutoff — no candle dated after it may be read or retained, directly or
transitively. `AssessRiskGateEvaluator`:
  - validates `as_of_date == gate_context.snapshot_date` when both are set
  - threads the cutoff into AggregateIndicatorsUseCase
  - bounds the LiquidityGate recent-candle enrichment fetch by the cutoff

All dates are FIXED (never `date.today()`). All tests run offline against a
local RecordingRepo (in-memory, records every get_candles() call).

Tests 8, 9, and 11 are anti-regression tests: they assert on RECORDED
repository calls / the LiquidityGate flip behavior, not just returned
values, so they would FAIL if `as_of_date` were ignored by the fix.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.dto.assess_risk import AssessRiskRequest
from src.application.use_case.assess_risk_gate_evaluator import AssessRiskGateEvaluator
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.rules.risk_gate import GateContext

_START = date(2026, 1, 1)
_TICKER = "BBCA"


def _liquid_candle(day: date) -> Candle:
    """close=10_000, volume=1_000_000 -> tx=10B IDR/day (2x the 5B floor)."""
    return Candle(
        ticker=_TICKER,
        date=day,
        open=Decimal("10000"),
        high=Decimal("10000"),
        low=Decimal("10000"),
        close=Decimal("10000"),
        volume=1_000_000,
    )


def _illiquid_candle(day: date) -> Candle:
    """close=1_000, volume=1_000_000 -> tx=1B IDR/day (below the 5B floor)."""
    return Candle(
        ticker=_TICKER,
        date=day,
        open=Decimal("1000"),
        high=Decimal("1000"),
        low=Decimal("1000"),
        close=Decimal("1000"),
        volume=1_000_000,
    )


def _liquid_series(count: int, start: date = _START) -> list[Candle]:
    return [_liquid_candle(start + timedelta(days=i)) for i in range(count)]


class RecordingRepo(MarketDataRepository):
    """Fake MarketDataRepository that records every get_candles() call.

    Mirrors MockMarketRepository (accumulation_screen_fixtures.py) for
    get_candles/get_date_range filtering, and additionally appends every
    (start_date, end_date) pair it is called with to self.calls, so tests
    can assert on what the production code actually asked for — not just
    what it got back.
    """

    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles
        self.calls: list[tuple[date | None, date | None]] = []

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        self.calls.append((start_date, end_date))
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        return bool(date_range and date_range[0] <= start_date and date_range[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if not rows:
            return None
        rows = sorted(rows, key=lambda c: c.date)
        return rows[0].date, rows[-1].date


def _make_evaluator(repo: MarketDataRepository, history_days: int = 300) -> AssessRiskGateEvaluator:
    return AssessRiskGateEvaluator(
        repository=repo,
        structural_gates=[LiquidityGate()],
        execution_gates=[],
        indicator_history_days=history_days,
        gate_recent_candle_lookback=20,
    )


class TestSnapshotDateBoundedByCutoff:
    def test_snapshot_date_bounded_by_cutoff(self):
        cutoff = _START + timedelta(days=150)
        candles = _liquid_series(260)
        repo = RecordingRepo(candles)
        evaluator = _make_evaluator(repo)

        request = AssessRiskRequest(
            ticker=_TICKER,
            gate_context=GateContext(ticker=_TICKER, snapshot_date=cutoff),
            as_of_date=cutoff,
        )
        response = evaluator.evaluate(request)

        assert response.assessment.snapshot_date <= cutoff


class TestAllGetCandlesCallsBoundedByCutoff:
    def test_all_get_candles_calls_bounded_by_cutoff(self):
        """KEY anti-regression: every repository.get_candles() call made while
        servicing a cutoff-bearing request must be bounded by that cutoff —
        both the indicator aggregation fetch and the LiquidityGate
        recent-candle enrichment fetch. No call may have end_date=None (that
        would silently read through to the live cache head)."""
        cutoff = _START + timedelta(days=150)
        candles = _liquid_series(260)
        repo = RecordingRepo(candles)
        evaluator = _make_evaluator(repo)

        request = AssessRiskRequest(
            ticker=_TICKER,
            gate_context=GateContext(ticker=_TICKER, snapshot_date=cutoff),
            as_of_date=cutoff,
        )
        evaluator.evaluate(request)

        assert repo.calls, "expected at least one get_candles() call to be recorded"
        assert all(end_date is not None for _, end_date in repo.calls)
        assert all(end_date <= cutoff for _, end_date in repo.calls)


class TestLiquidityGateFlipGoesToShape:
    def test_liquidity_gate_flip_goto_shape(self):
        """Must fail on pre-fix code (as_of_date ignored).

        History layout: candles[0..259] are LIQUID (close=10_000,
        volume=1_000_000 -> 10B tx/day), candles[260..279] are ILLIQUID
        (close=1_000, volume=1_000_000 -> 1B tx/day). Cutoff is pinned to the
        last liquid date (day 259):
          - the 20-candle window ENDING AT the cutoff is entirely liquid
            candles -> LiquidityGate must NOT fire at the cutoff.
          - the 20-candle window ENDING AT the cache head (day 279) is
            entirely illiquid candles -> LiquidityGate DOES fire live.

        If as_of_date were ignored, the cutoff-bearing assessment would (like
        the live one) read through to the cache head and see the illiquid
        tail, incorrectly firing LiquidityGate at the cutoff too.
        """
        cutoff = _START + timedelta(days=259)  # last liquid date
        liquid = _liquid_series(260, start=_START)
        illiquid_tail_start = _START + timedelta(days=260)
        illiquid = [_illiquid_candle(illiquid_tail_start + timedelta(days=i)) for i in range(20)]
        candles = liquid + illiquid
        cache_head = candles[-1].date

        repo_at_cutoff = RecordingRepo(list(candles))
        evaluator_at_cutoff = _make_evaluator(repo_at_cutoff)
        response_at_cutoff = evaluator_at_cutoff.evaluate(
            AssessRiskRequest(
                ticker=_TICKER,
                gate_context=GateContext(ticker=_TICKER, snapshot_date=cutoff),
                as_of_date=cutoff,
            )
        )
        assert response_at_cutoff.assessment.gate_triggered is None

        repo_live = RecordingRepo(list(candles))
        evaluator_live = _make_evaluator(repo_live)
        response_live = evaluator_live.evaluate(
            AssessRiskRequest(
                ticker=_TICKER,
                gate_context=GateContext(ticker=_TICKER, snapshot_date=cache_head),
                as_of_date=None,
            )
        )
        assert response_live.assessment.gate_triggered == "LiquidityGate"


class TestMismatchAsOfAndSnapshotDateRaises:
    def test_mismatch_as_of_and_snapshot_date_raises(self):
        as_of = _START + timedelta(days=150)
        snapshot_date = _START + timedelta(days=151)
        candles = _liquid_series(260)
        repo = RecordingRepo(candles)
        evaluator = _make_evaluator(repo)

        request = AssessRiskRequest(
            ticker=_TICKER,
            gate_context=GateContext(ticker=_TICKER, snapshot_date=snapshot_date),
            as_of_date=as_of,
        )

        with pytest.raises(ValueError) as exc_info:
            evaluator.evaluate(request)

        message = str(exc_info.value)
        assert str(as_of) in message
        assert str(snapshot_date) in message


class TestNoCandlesAtOrBeforeCutoffRaisesAndNoUnboundedRetry:
    def test_no_candles_at_or_before_cutoff_raises_and_no_unbounded_retry(self):
        candles = _liquid_series(260)
        earliest = candles[0].date
        cutoff = earliest - timedelta(days=1)
        repo = RecordingRepo(candles)
        evaluator = _make_evaluator(repo)

        request = AssessRiskRequest(
            ticker=_TICKER,
            gate_context=GateContext(ticker=_TICKER, snapshot_date=cutoff),
            as_of_date=cutoff,
        )

        with pytest.raises(ValueError) as exc_info:
            evaluator.evaluate(request)

        assert str(cutoff) in str(exc_info.value)
        # No unbounded fallback: no get_candles() call may have been made
        # with end_date=None (which would silently read through to the live
        # cache head after the bounded read came back empty).
        assert all(end_date is not None for _, end_date in repo.calls)


class TestCutoffAfterCacheHeadEqualsLive:
    def test_cutoff_after_cache_head_equals_live(self):
        candles = _liquid_series(260)
        cache_head = candles[-1].date

        repo_cutoff = RecordingRepo(list(candles))
        evaluator_cutoff = _make_evaluator(repo_cutoff)
        response_cutoff = evaluator_cutoff.evaluate(
            AssessRiskRequest(
                ticker=_TICKER,
                gate_context=GateContext(ticker=_TICKER, snapshot_date=cache_head),
                as_of_date=cache_head,
            )
        )

        repo_live = RecordingRepo(list(candles))
        evaluator_live = _make_evaluator(repo_live)
        response_live = evaluator_live.evaluate(
            AssessRiskRequest(
                ticker=_TICKER,
                gate_context=GateContext(ticker=_TICKER, snapshot_date=cache_head),
                as_of_date=None,
            )
        )

        assert response_cutoff.assessment.gate_triggered == response_live.assessment.gate_triggered
        assert response_cutoff.assessment.snapshot_date == response_live.assessment.snapshot_date
