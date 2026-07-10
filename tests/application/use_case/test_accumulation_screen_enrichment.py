"""Enrichment and signal attachment behavior tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
)
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from src.application.use_case.assess_signal_use_case import (
    AssessSignalRequest,
    AssessSignalUseCase,
)
from src.domain.value_objects.analyst_consensus import AnalystConsensus
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.signal_assessment import (
    SignalContext,
    SignalStrength,
)
from src.domain.value_objects.ticker_notation import (
    TickerNotation,
    TickerNotationSnapshot,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    MockBrokerRepository,
    MockMarketRepository,
    _candle,
    _summary,
    _weekdays,
)


class MockTickerNotationProvider:
    def get_notation(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> TickerNotationSnapshot | None:
        return TickerNotationSnapshot(
            ticker=ticker.upper(),
            status="STATUS_ACTIVE",
            listing_board="Papan Pemantauan Khusus",
            haircut_percentage="100%",
            notations=[TickerNotation(code="X", description="Special monitoring")],
        )


class FutureOnlyAnalystProvider:
    def __init__(self, future_date: date):
        self.future_date = future_date
        self.calls = []

    def get_consensus(self, ticker: str, as_of_date: date | None = None):
        self.calls.append((ticker, as_of_date))
        if as_of_date is not None and self.future_date > as_of_date:
            return None
        return AnalystConsensus(
            ticker=ticker.upper(),
            buy_count=10,
            hold_count=0,
            sell_count=0,
            avg_price_target=150.0,
            current_price=100.0,
            last_updated=self.future_date,
        )


class FutureOnlyForwardEstimatesProvider:
    def __init__(self, future_date: date):
        self.future_date = future_date
        self.calls = []

    def get_forward_estimates(self, ticker: str, as_of_date: date | None = None):
        self.calls.append((ticker, as_of_date))
        if as_of_date is not None and self.future_date > as_of_date:
            return None
        return ForwardEstimates(
            ticker=ticker.upper(),
            forward_eps_1y=10.0,
            revenue_forward_1y=None,
            current_price=100.0,
            forward_pe=10.0,
        )


class FutureOnlyTickerNotationProvider:
    def __init__(self, future_date: date):
        self.future_date = future_date
        self.calls = []

    def get_notation(self, ticker: str, as_of_date: date | None = None):
        self.calls.append((ticker, as_of_date))
        if as_of_date is not None and self.future_date > as_of_date:
            return None
        return TickerNotationSnapshot(
            ticker=ticker.upper(),
            status="STATUS_ACTIVE",
        )


def test_screen_attaches_ticker_notation_without_changing_score():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BTEK", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BTEK", day, Decimal("110")) for day in session_dates]

    base = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
    ).execute(
        AccumulationScreenRequest(
            tickers=["BTEK"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    enriched = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        ticker_notation_provider=MockTickerNotationProvider(),
    ).execute(
        AccumulationScreenRequest(
            tickers=["BTEK"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert enriched.candidates[0].ticker_notation is not None
    assert enriched.candidates[0].ticker_notation.notations[0].code == "X"
    assert enriched.candidates[0].foreign_flow_score == base.candidates[0].foreign_flow_score
    assert enriched.candidates[0].foreign_flow_evidence is not None
    assert (
        enriched.candidates[0].foreign_flow_evidence.composite_score
        == enriched.candidates[0].foreign_flow_score
    )
    candidate_dict = enriched.candidates[0].to_dict()
    assert candidate_dict["foreign_flow_score"] == enriched.candidates[0].foreign_flow_score
    assert "composite_foreign_flow_score" not in candidate_dict
    assert candidate_dict["ticker_notation"]["notations"][0]["code"] == "X"


def test_historical_screen_uses_as_of_date_for_point_in_time_enrichment():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    future_date = as_of + timedelta(days=10)
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    analyst = FutureOnlyAnalystProvider(future_date)
    forward = FutureOnlyForwardEstimatesProvider(future_date)
    notation = FutureOnlyTickerNotationProvider(future_date)

    response = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        analyst_consensus_provider=analyst,
        forward_estimates_provider=forward,
        ticker_notation_provider=notation,
    ).execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    candidate = response.candidates[0]
    assert analyst.calls == [("BBCA", as_of)]
    assert forward.calls == [("BBCA", as_of)]
    assert notation.calls == [("BBCA", as_of)]
    assert candidate.analyst_consensus is None
    assert candidate.forward_estimates is None
    assert candidate.ticker_notation is None


def test_live_screen_passes_none_as_of_date_to_fetch_capable_enrichment():
    session_dates = _weekdays(date.today() - timedelta(days=14), 7)
    candles = [
        _candle("BBCA", date.today() - timedelta(days=i), Decimal("100"))
        for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    analyst = FutureOnlyAnalystProvider(date.today())
    forward = FutureOnlyForwardEstimatesProvider(date.today())
    notation = FutureOnlyTickerNotationProvider(date.today())

    response = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        analyst_consensus_provider=analyst,
        forward_estimates_provider=forward,
        ticker_notation_provider=notation,
    ).execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=None,
        )
    )

    assert response.candidates
    assert analyst.calls == [("BBCA", None)]
    assert forward.calls == [("BBCA", None)]
    assert notation.calls == [("BBCA", None)]


def _assess(
    flow_score: float = 50.0,
    bandar_broad_score: int | None = None,
    bandar_max_range: int = 6,
    insider_net_buy_ratio: float | None = None,
    seasonality_win_rate: float | None = None,
    seasonality_avg_return_pct: float | None = None,
    seasonality_total_years: int | None = None,
    seasonality_back_years: int | None = None,
    analyst_buy_pct: float | None = None,
    analyst_upside_pct: float | None = None,
    forward_pe: float | None = None,
):
    """Build a SignalContext from screener-path data and run AssessSignalUseCase."""
    ctx = SignalContext(
        ticker="TEST",
        snapshot_date=date.today(),
        foreign_flow_quality=min(flow_score, 100.0) / 100.0,
        bandar_broad_score=bandar_broad_score,
        bandar_max_range=bandar_max_range,
        insider_net_buy_ratio=insider_net_buy_ratio,
        seasonality_win_rate=seasonality_win_rate,
        seasonality_avg_return_pct=seasonality_avg_return_pct,
        seasonality_total_years=seasonality_total_years,
        seasonality_back_years=seasonality_back_years,
        analyst_buy_pct=analyst_buy_pct,
        analyst_upside_pct=analyst_upside_pct,
        forward_pe=forward_pe,
    )
    return AssessSignalUseCase().execute(AssessSignalRequest(ticker="TEST", signal_context=ctx))


def test_signal_all_neutral_when_no_enrichment():
    sa = _assess(flow_score=50.0)
    assert sa.assessment.score == 50
    bd = sa.assessment.breakdown_dict
    assert bd["bandar_intensity"] == 50.0
    assert bd["insider_activity"] == 50.0
    assert bd["seasonality_edge"] == 50.0
    assert bd["analyst_consensus"] == 50.0
    assert bd["forward_valuation"] == 50.0


def test_screen_derives_forward_pe_from_latest_price_when_cache_has_eps_only():
    from unittest.mock import MagicMock

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    forward_provider = MagicMock()
    forward_provider.get_forward_estimates.return_value = ForwardEstimates(
        ticker="BBCA",
        forward_eps_1y=10.0,
        revenue_forward_1y=None,
        current_price=None,
        forward_pe=None,
    )

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        forward_estimates_provider=forward_provider,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    candidate = response.candidates[0]
    assert candidate.forward_estimates is not None
    assert candidate.forward_estimates.forward_pe == 10.0
    assert "VALUATION_STRETCHED" not in candidate.signal_assessment.active_flags


def test_signal_insider_full_buy_raises_score():
    sa = _assess(flow_score=50.0, insider_net_buy_ratio=1.0)
    bd = sa.assessment.breakdown_dict
    assert bd["insider_activity"] == pytest.approx(100.0)
    assert sa.assessment.score > 50


def test_signal_analyst_all_buy_full_upside():
    sa = _assess(flow_score=50.0, analyst_buy_pct=1.0, analyst_upside_pct=30.0)
    bd = sa.assessment.breakdown_dict
    assert bd["analyst_consensus"] == 100.0
    assert sa.assessment.score > 50


def test_signal_seasonality_tailwind_uses_win_rate():
    sa = _assess(
        flow_score=50.0,
        seasonality_win_rate=80.0,
        seasonality_avg_return_pct=2.5,
        seasonality_total_years=5,
        seasonality_back_years=5,
    )
    bd = sa.assessment.breakdown_dict
    assert bd["seasonality_edge"] == 80.0


def test_signal_bandar_full_accumulation():
    sa = _assess(flow_score=50.0, bandar_broad_score=10, bandar_max_range=12)
    bd = sa.assessment.breakdown_dict
    assert bd["bandar_intensity"] > 85.0


def test_signal_strong_when_multiple_factors_elevated():
    sa = _assess(
        flow_score=91.7,
        insider_net_buy_ratio=1.0,
        analyst_buy_pct=0.8,
        analyst_upside_pct=20.0,
        seasonality_win_rate=75.0,
        seasonality_avg_return_pct=1.5,
        seasonality_total_years=5,
        seasonality_back_years=5,
        bandar_broad_score=4,
        bandar_max_range=6,
    )
    assert sa.assessment.strength == SignalStrength.STRONG
    assert sa.assessment.score > 70


def test_screener_populates_signal_assessment():
    """AccumulationScreenUseCase must populate signal_assessment on each candidate."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    uc = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
    )
    resp = uc.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=0,
            min_foreign_flow_score=0.0,
            min_foreign_flow_score_enabled=True,
            as_of_date=as_of,
        )
    )
    assert resp.candidates, "expected at least one candidate"
    c = resp.candidates[0]
    assert c.signal_assessment is not None, "signal_assessment must be populated"
    assert 0 <= c.signal_assessment.assessment.score <= 100


def test_candidate_to_dict_emits_canonical_coverage_score():
    """Candidate.to_dict() signal_assessment block must include canonical coverage_score."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    uc = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
    )
    resp = uc.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=0,
            min_foreign_flow_score=0.0,
            min_foreign_flow_score_enabled=True,
            as_of_date=as_of,
        )
    )
    c = resp.candidates[0]
    assert c.signal_assessment is not None
    d = c.to_dict()
    sa_dict = d["signal_assessment"]
    assert "coverage_score" in sa_dict
    assert "confidence_score" in sa_dict
    assert sa_dict["coverage_score"] == sa_dict["confidence_score"]
    assert sa_dict["coverage_score"] is not None
