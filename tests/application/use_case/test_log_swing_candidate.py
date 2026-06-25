"""Tests for LogSwingCandidateUseCase."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenResponse,
)
from src.application.use_case.log_swing_candidate_use_case import (
    LogSwingCandidateRequest,
    LogSwingCandidateUseCase,
)
from src.domain.value_objects.market_context import MarketRegime, MarketContext

# ---------------------------------------------------------------------------
# Fakes / stubs
# ---------------------------------------------------------------------------

class FakeScreenUseCase:
    """Returns a canned AccumulationCandidate keyed by (ticker, window_days)."""

    def __init__(self, candidates: dict[tuple[str, int], AccumulationCandidate | None]):
        self._candidates = candidates

    def execute(self, request: AccumulationScreenRequest) -> AccumulationScreenResponse:
        ticker = request.tickers[0]
        candidate = self._candidates.get((ticker, request.window_days))
        return AccumulationScreenResponse(
            candidates=[candidate] if candidate is not None else [],
            screened_at=date(2025, 1, 15),
            window_days=request.window_days,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="idx",
        )


class FakeJournalService:
    def __init__(self, return_count: int = 1):
        self.calls: list[dict] = []
        self._count = return_count

    def log_candidate(self, **kwargs: Any) -> int:
        self.calls.append(kwargs)
        return self._count


class FakeTradeStore:
    def __init__(self):
        self.records: list[dict] = []

    def append(self, record: dict) -> bool:
        self.records.append(record)
        return True


class FakeMarketRepository:
    def __init__(self, close: Decimal | None = None):
        self._close = close

    def get_candles(self, ticker: str, start_date=None, end_date=None):
        if self._close is None:
            return []
        return [SimpleNamespace(ticker=ticker, close=self._close)]

    def save_candles(self, candles):
        pass


class FakeRegimeUseCase:
    def __init__(self, regime: str = "RISK_ON"):
        self._regime = regime

    def evaluate(self, as_of_date: date | None = None) -> MarketContext:
        """Return a minimal MarketContext with the specified regime."""
        regime_enum = MarketRegime(self._regime)
        return MarketContext(
            regime=regime_enum,
            conviction=0.5,
            factors=(),
            signal_multiplier=1.0,
            gate_tightening=False,
            as_of_date=as_of_date or date.today(),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(
    ticker: str = "BBCA",
    window_days: int = 7,
    score: float = 70.0,
    trend: str = "UP",
    vwap_discount_pct: float = 3.0,
    avg_flow_ratio: float = 10.0,
    rsi: float = 50.0,
) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
        window_days=window_days,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("5000000"),
        consecutive_streak=4,
        foreign_vwap=Decimal("9800"),
        current_price=Decimal("10000"),
        vwap_discount_pct=vwap_discount_pct,
        rsi=rsi,
        trend=trend,
        accum_score=score,
        top_brokers=None,
        institutional_flag=False,
        avg_flow_ratio=avg_flow_ratio,
    )


def _make_request(
    ticker: str = "BBCA",
    window_days: int = 7,
    entry_price: Decimal | None = None,
    from_analysis: bool = True,
    preset: str | None = "foreign-bounce",
    with_regime: bool = False,
    regime_universe: list[str] | None = None,
) -> LogSwingCandidateRequest:
    return LogSwingCandidateRequest(
        ticker=ticker,
        window_days=window_days,
        entry_price=entry_price,
        from_analysis=from_analysis,
        preset=preset,
        with_regime=with_regime,
        regime_universe=regime_universe or [],
        benchmark_ticker="COMPOSITE",
        logged_at=date(2025, 1, 15),
        tier1_broker_codes=frozenset({"MS", "DB"}),
        sector_breadth_enabled=False,
        sector_breadth_threshold=0.6,
        sector_breadth_bonus_pts=10.0,
        sector_breadth_min_tickers=3,
        gate_min_score=60.0,
        gate_min_vwap_discount_pct=2.0,
        gate_required_trend="UP",
        gate_min_flow_ratio_pct=5.0,
        gate_max_rsi=65.0,
        watch_max_failed_gates=1,
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
        max_hold_days=10,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_logs_candidate_and_returns_written_true():
    candidate = _make_candidate()
    screen = FakeScreenUseCase({("BBCA", 7): candidate, ("BBCA", 30): None, ("BBCA", 90): None})
    journal = FakeJournalService(return_count=1)
    trade_store = FakeTradeStore()
    market = FakeMarketRepository(close=Decimal("10000"))

    uc = LogSwingCandidateUseCase(
        screen_use_case=screen,
        journal_service=journal,
        market_repository=market,
        trade_journal_store=trade_store,
    )
    result = uc.execute(_make_request())

    assert result.written is True
    assert result.classification == "ENTER"
    assert result.candidate_score == pytest.approx(70.0)
    assert len(journal.calls) == 1
    assert len(trade_store.records) == 1


def test_duplicate_returns_written_false_and_no_jsonl():
    candidate = _make_candidate()
    screen = FakeScreenUseCase({("BBCA", 7): candidate, ("BBCA", 30): None, ("BBCA", 90): None})
    journal = FakeJournalService(return_count=0)  # 0 = duplicate
    trade_store = FakeTradeStore()
    market = FakeMarketRepository(close=Decimal("10000"))

    uc = LogSwingCandidateUseCase(
        screen_use_case=screen,
        journal_service=journal,
        market_repository=market,
        trade_journal_store=trade_store,
    )
    result = uc.execute(_make_request())

    assert result.written is False
    assert len(trade_store.records) == 0  # JSONL write skipped on duplicate


def test_from_analysis_false_skips_gate_evaluation():
    candidate = _make_candidate()
    screen = FakeScreenUseCase({("BBCA", 7): candidate, ("BBCA", 30): None, ("BBCA", 90): None})
    journal = FakeJournalService()
    market = FakeMarketRepository(close=Decimal("10000"))

    uc = LogSwingCandidateUseCase(
        screen_use_case=screen,
        journal_service=journal,
        market_repository=market,
    )
    result = uc.execute(_make_request(from_analysis=False, preset=None))

    assert result.classification is None
    assert result.planned_stop is None
    assert result.planned_target is None
    assert result.failed_gates == ()


def test_with_regime_populates_regime_label():
    candidate = _make_candidate()
    screen = FakeScreenUseCase({("BBCA", 7): candidate, ("BBCA", 30): None, ("BBCA", 90): None})
    journal = FakeJournalService()
    market = FakeMarketRepository(close=Decimal("10000"))
    regime_uc = FakeRegimeUseCase(regime="RISK_ON")

    uc = LogSwingCandidateUseCase(
        screen_use_case=screen,
        journal_service=journal,
        market_repository=market,
        regime_use_case=regime_uc,
    )
    result = uc.execute(_make_request(with_regime=True))

    assert result.regime == "RISK_ON"
    assert journal.calls[0]["regime"] == "RISK_ON"


def test_no_candidate_found_produces_avoid_and_zero_score():
    screen = FakeScreenUseCase({})  # no candidates for any window
    journal = FakeJournalService()
    market = FakeMarketRepository()

    uc = LogSwingCandidateUseCase(
        screen_use_case=screen,
        journal_service=journal,
        market_repository=market,
    )
    result = uc.execute(_make_request())

    assert result.candidate_score is None
    assert result.classification == "AVOID"
    assert "No accumulation/broker-flow candidate available" in result.failed_gates
    assert result.entry_price == Decimal("0")


def test_multi_window_all_hot_produces_sustained_pattern():
    candidates_map = {
        ("BBCA", 7): _make_candidate(score=70.0),
        ("BBCA", 30): _make_candidate(score=70.0),
        ("BBCA", 90): _make_candidate(score=70.0),
    }
    screen = FakeScreenUseCase(candidates_map)
    journal = FakeJournalService()
    market = FakeMarketRepository(close=Decimal("10000"))

    uc = LogSwingCandidateUseCase(
        screen_use_case=screen,
        journal_service=journal,
        market_repository=market,
    )
    result = uc.execute(_make_request())

    assert result.pattern == "sustained"
    assert journal.calls[0]["pattern"] == "sustained"


import pytest
