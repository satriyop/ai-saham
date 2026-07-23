"""Enrichment and signal attachment behavior tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from src.domain.value_objects.analyst_consensus import AnalystConsensus
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.ticker_notation import (
    TickerNotation,
    TickerNotationSnapshot,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    _candle,
    _summary,
    _weekdays,
    make_signal_evidence_execution_context,
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
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    ).execute(
        AccumulationScreenRequest(
            tickers=["BTEK"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )

    enriched = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        ticker_notation_provider=MockTickerNotationProvider(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    ).execute(
        AccumulationScreenRequest(
            tickers=["BTEK"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )

    assert enriched.candidates[0].ticker_notation is not None
    assert enriched.candidates[0].ticker_notation.notations[0].code == "X"
    assert enriched.candidates[0].accum_score == base.candidates[0].accum_score
    assert enriched.candidates[0].foreign_flow_evidence is not None
    assert (
        enriched.candidates[0].foreign_flow_evidence.signal_score
        == enriched.candidates[0].accum_score
    )
    candidate_dict = enriched.candidates[0].to_dict()
    assert candidate_dict["accum_score"] == enriched.candidates[0].accum_score
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
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        analyst_consensus_provider=analyst,
        forward_estimates_provider=forward,
        ticker_notation_provider=notation,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    ).execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
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
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        analyst_consensus_provider=analyst,
        forward_estimates_provider=forward,
        ticker_notation_provider=notation,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    ).execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=None,
        ),
        execution_context=make_signal_evidence_execution_context(date.today()),
    )

    assert response.candidates
    assert analyst.calls == [("BBCA", None)]
    assert forward.calls == [("BBCA", None)]
    assert notation.calls == [("BBCA", None)]


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
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        forward_estimates_provider=forward_provider,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )

    candidate = response.candidates[0]
    assert candidate.forward_estimates is not None
    assert candidate.forward_estimates.forward_pe == 10.0
    assert "VALUATION_STRETCHED" not in candidate.signal_assessment.active_flags


def test_screener_populates_signal_assessment():
    """AccumulationScreenUseCase must populate signal_assessment on each candidate."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    uc = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    resp = uc.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=0,
            min_accum_score=0.0,
            min_accum_score_enabled=True,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert resp.candidates, "expected at least one candidate"
    c = resp.candidates[0]
    assert c.signal_assessment is not None, "signal_assessment must be populated"
    assert 0 <= c.signal_assessment.assessment.score <= 100


def test_candidate_to_dict_emits_canonical_signal_authority_coverage():
    """Candidate.to_dict() signal_assessment block must include canonical
    signal_authority_coverage and no removed aliases."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    uc = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    resp = uc.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=0,
            min_accum_score=0.0,
            min_accum_score_enabled=True,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    c = resp.candidates[0]
    assert c.signal_assessment is not None
    d = c.to_dict()
    sa_dict = d["signal_assessment"]
    assert "signal_authority_coverage" in sa_dict
    assert sa_dict["signal_authority_coverage"] is not None
    assert "coverage_score" not in sa_dict
    assert "confidence_score" not in sa_dict
