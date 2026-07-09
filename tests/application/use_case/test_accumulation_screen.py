"""Tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.use_case.accumulation_screen_use_case import (
    BCI_CLUSTER,
    BCI_RETAIL,
    BCI_STABLE,
    TIER1_FOREIGN_BROKERS,
    AccumulationDerivedFeaturePolicy,
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.analyst_consensus import AnalystConsensus
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.ticker_notation import TickerNotation, TickerNotationSnapshot
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus


class MockMarketRepository(MarketDataRepository):
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def save_candles(self, candles: list[Candle]) -> None:
        self._candles.extend(candles)

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        rows = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date is not None:
            rows = [c for c in rows if c.date >= start_date]
        if end_date is not None:
            rows = [c for c in rows if c.date <= end_date]
        return sorted(rows, key=lambda c: c.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        return bool(date_range and date_range[0] <= start_date and date_range[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_candles(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


class MockBrokerRepository(BrokerDataRepository):
    def __init__(self, summaries: list[BrokerSummary]) -> None:
        self._summaries = summaries

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        self._summaries.append(summary)

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        self._summaries.extend(summaries)

    def get_broker_summary(self, ticker: str, target_date: date) -> BrokerSummary | None:
        for summary in self._summaries:
            if summary.ticker == ticker.upper() and summary.date == target_date:
                return summary
        return None

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerSummary]:
        rows = [s for s in self._summaries if s.ticker == ticker.upper()]
        if start_date is not None:
            rows = [s for s in rows if s.date >= start_date]
        if end_date is not None:
            rows = [s for s in rows if s.date <= end_date]
        return sorted(rows, key=lambda s: s.date)

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        return bool(date_range and date_range[0] <= start_date and date_range[1] >= end_date)

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_broker_summaries(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date


class RecordingInsiderProvider:
    def __init__(self) -> None:
        self.calls = []

    def get_insider_transactions(
        self,
        ticker,
        from_date,
        to_date,
        action_type="BUY",
        as_of_date=None,
    ):
        self.calls.append(
            {
                "ticker": ticker,
                "from_date": from_date,
                "to_date": to_date,
                "action_type": action_type,
                "as_of_date": as_of_date,
            }
        )
        return []


def _candle(ticker: str, day: date, close: Decimal) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
    )


def _summary(ticker: str, day: date, foreign_vwap: Decimal) -> BrokerSummary:
    buy_lot = 10_000
    buy_value = foreign_vwap * Decimal(buy_lot * 100)
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=buy_value,
        foreign_sell_value=Decimal("0"),
        foreign_buy_lot=buy_lot,
        foreign_sell_lot=0,
        total_value=buy_value * Decimal("2"),
        total_lot=buy_lot * 2,
    )


def _weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def test_screen_window_uses_latest_broker_sessions_not_calendar_days():
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
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
    assert candidate.total_days == 7
    assert candidate.net_buy_days == 7
    assert candidate.consecutive_streak == 7
    assert candidate.window_days == 7


def test_screen_passes_as_of_date_to_insider_provider():
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    insider_provider = RecordingInsiderProvider()

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        insider_activity_provider=insider_provider,
    )

    use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert insider_provider.calls
    assert insider_provider.calls[0]["ticker"] == "BBCA"
    assert insider_provider.calls[0]["action_type"] == "ALL"
    assert insider_provider.calls[0]["as_of_date"] == as_of


def test_screen_ignores_unsafe_broker_summary_rows():
    session_dates = _weekdays(date(2026, 1, 1), 8)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    valid_summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates[:-1]]
    unsafe_latest = BrokerSummary(
        ticker="BBCA",
        date=session_dates[-1],
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=Decimal("999999999999"),
        foreign_sell_value=Decimal("0"),
        foreign_buy_lot=10_000,
        foreign_sell_lot=0,
        total_value=Decimal("0"),
        total_lot=0,
    )

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository([*valid_summaries, unsafe_latest]),
        market_repository=MockMarketRepository(candles),
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
    assert candidate.total_days == 7
    assert candidate.net_buy_days == 7
    assert candidate.total_net_value == sum(
        (s.foreign_net_value for s in valid_summaries),
        Decimal("0"),
    )


def test_screen_uses_derived_feature_policy_for_trend_threshold():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candle_dates = _weekdays(date(2025, 12, 1), 25)
    candles = [_candle("BBCA", day, Decimal("100")) for day in candle_dates[:-1]] + [
        _candle("BBCA", candle_dates[-1], Decimal("103"))
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    loose_threshold = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        derived_feature_policy=AccumulationDerivedFeaturePolicy(
            trend_sma_period=20,
            trend_threshold_pct=5.0,
        ),
    )
    strict_threshold = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        derived_feature_policy=AccumulationDerivedFeaturePolicy(
            trend_sma_period=20,
            trend_threshold_pct=2.0,
        ),
    )

    request = AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        as_of_date=as_of,
    )

    assert loose_threshold.execute(request).candidates[0].trend == "SIDE"
    assert strict_threshold.execute(request).candidates[0].trend == "UP"


def _daily_flow(ticker: str, day: date, broker_code: str, net_lot: int) -> BrokerDailyFlow:
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=broker_code,
        broker_name=broker_code,
        date=day,
        buy_lot=max(net_lot, 0),
        sell_lot=max(-net_lot, 0),
        net_lot=net_lot,
        buy_value=Decimal(max(net_lot, 0) * 100 * 1000),
        sell_value=Decimal(max(-net_lot, 0) * 100 * 1000),
        net_value=Decimal(net_lot * 100 * 1000),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
        avg_price=Decimal("1000"),
        buy_pct=0.0,
        sell_pct=0.0,
    )


class MockBrokerRepositoryWithDaily(MockBrokerRepository):
    def __init__(
        self,
        summaries: list[BrokerSummary],
        daily_flows: list[BrokerDailyFlow] | None = None,
    ) -> None:
        super().__init__(summaries)
        self._daily_flows = daily_flows or []

    def get_broker_daily_flows(
        self,
        ticker: str,
        start_date=None,
        end_date=None,
        broker_codes=None,
        source=None,
    ) -> list[BrokerDailyFlow]:
        rows = [f for f in self._daily_flows if f.ticker == ticker.upper()]
        if start_date:
            rows = [f for f in rows if f.date >= start_date]
        if end_date:
            rows = [f for f in rows if f.date <= end_date]
        if broker_codes:
            rows = [f for f in rows if f.broker_code in broker_codes]
        return sorted(rows, key=lambda f: (f.date, f.broker_code))


def _make_use_case(summaries, daily_flows=None):
    session_dates = _weekdays(date(2026, 1, 1), 10)
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    return (
        AccumulationScreenUseCase(
            broker_repository=MockBrokerRepositoryWithDaily(summaries, daily_flows),
            market_repository=MockMarketRepository(candles),
        ),
        session_dates,
    )


def test_bci_cluster_when_three_or_more_tier1_codes_are_net_buyers():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # AK, BK, ZP are all Tier 1 → should produce CLUSTER
    daily_flows = [
        _daily_flow("BBCA", session_dates[0], "AK", 100),
        _daily_flow("BBCA", session_dates[0], "BK", 80),
        _daily_flow("BBCA", session_dates[0], "ZP", 60),
        _daily_flow("BBCA", session_dates[1], "AK", 50),
    ]
    use_case, _ = _make_use_case(summaries, daily_flows)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    assert c.bci_label == BCI_CLUSTER
    assert c.bci_tier1_count == 3
    assert c.foreign_flow_score_breakdown.breakdown_dict["inst"] == 12.5


def test_bci_stable_when_one_or_two_tier1_codes_are_net_buyers():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # Only AK (Tier 1) + YP (domestic, not Tier 1)
    daily_flows = [
        _daily_flow("BBCA", session_dates[0], "AK", 100),
        _daily_flow("BBCA", session_dates[0], "YP", 200),  # YP is domestic, not Tier 1
    ]
    use_case, _ = _make_use_case(summaries, daily_flows)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    assert c.bci_label == BCI_STABLE
    assert c.bci_tier1_count == 1
    assert c.foreign_flow_score_breakdown.breakdown_dict["inst"] == 4.2


def test_bci_retail_when_no_tier1_codes_are_net_buyers():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # YP (domestic) only — no Tier 1 codes
    daily_flows = [
        _daily_flow("BBCA", session_dates[0], "YP", 300),
    ]
    use_case, _ = _make_use_case(summaries, daily_flows)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    assert c.bci_label == BCI_RETAIL
    assert c.bci_tier1_count == 0
    assert c.foreign_flow_score_breakdown.breakdown_dict["inst"] == 0.0


def test_bci_none_when_no_daily_flow_data():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    use_case, _ = _make_use_case(summaries, daily_flows=None)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    assert c.bci_label is None
    assert c.bci_tier1_count == 0
    assert c.foreign_flow_score_breakdown.breakdown_dict["inst"] == 0.0


def test_bci_counts_all_net_buyers_not_just_top5():
    """A Tier 1 code ranked 6th overall still counts toward BCI tier."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # 5 domestic/non-Tier1 codes with big lots + AK (Tier 1) in 6th place
    daily_flows = [
        _daily_flow("BBCA", session_dates[0], "YP", 1000),
        _daily_flow("BBCA", session_dates[0], "PD", 900),
        _daily_flow("BBCA", session_dates[0], "XL", 800),
        _daily_flow("BBCA", session_dates[0], "XC", 700),
        _daily_flow("BBCA", session_dates[0], "DR", 600),  # DR is Tier 1
        _daily_flow("BBCA", session_dates[0], "AK", 50),  # AK Tier 1, rank 6
    ]
    use_case, _ = _make_use_case(summaries, daily_flows)

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    c = response.candidates[0]

    # Both AK and DR are Tier 1 — STABLE (2 codes)
    assert c.bci_label == BCI_STABLE
    assert c.bci_tier1_count == 2


# ── tier1_broker_codes passable via request ───────────────────────────────


def test_tier1_codes_default_to_module_constant():
    req = AccumulationScreenRequest(tickers=["BBCA"])
    assert req.tier1_broker_codes == TIER1_FOREIGN_BROKERS


def test_tier1_codes_override_changes_bci():
    """Passing a custom tier1 set changes which brokers count for BCI."""
    as_of = date(2026, 6, 1)
    session_dates = [as_of - timedelta(days=i) for i in range(3)]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    # Only YP is a net buyer — YP is NOT in default TIER1_FOREIGN_BROKERS
    daily_flows = [_daily_flow("BBCA", session_dates[0], "YP", 500)]
    use_case, _ = _make_use_case(summaries, daily_flows)

    # Default tier1: YP not included → BCI RETAIL
    resp_default = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"], window_days=7, min_net_buy_days=1, as_of_date=as_of
        )
    )
    assert resp_default.candidates[0].bci_label == BCI_RETAIL

    # Custom tier1 including YP → BCI STABLE
    resp_custom = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            tier1_broker_codes=frozenset({"YP"}),
        )
    )
    assert resp_custom.candidates[0].bci_label == BCI_STABLE


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
    assert enriched.candidates[0].ticker_notation.codes == ["X"]
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


# ─── Signal Assessment (migrated from _composite_score) ──────────────────────
#
# These tests verify behavioral parity with the deleted _composite_score().
# They now use AssessSignalUseCase + SignalContext directly (the public API)
# instead of the removed internal function.

from datetime import date as _date
from decimal import Decimal as _Decimal

from src.application.use_case.assess_signal_use_case import AssessSignalRequest, AssessSignalUseCase
from src.domain.value_objects.signal_assessment import SignalContext, SignalStrength


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
        snapshot_date=_date.today(),
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
    # score=50 → foreign_quality=0.5 → foreign component=50.0; all others neutral=50
    # total = 50 (all factors neutral) → score=50
    sa = _assess(flow_score=50.0)
    assert sa.assessment.score == 50
    bd = sa.assessment.breakdown_dict
    # All components should be 50 (neutral)
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
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), _Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, _Decimal("110")) for day in session_dates]
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
    assert candidate.forward_estimates.forward_pe == 10.0  # PE derived from eps + close price
    # Phase 4: PE=10 is far below VALUATION_STRETCHED threshold (50) → no penalty flag
    assert "VALUATION_STRETCHED" not in candidate.signal_assessment.active_flags


def test_signal_insider_full_buy_raises_score():
    sa = _assess(flow_score=50.0, insider_net_buy_ratio=1.0)
    # insider_component = (+1.0+1.0)/2*100 = 100.0
    bd = sa.assessment.breakdown_dict
    assert bd["insider_activity"] == pytest.approx(100.0)
    assert sa.assessment.score > 50


def test_signal_analyst_all_buy_full_upside():
    # buy_pct=1.0 → buy_score=60; upside=30% → upside_score=40; analyst=100
    sa = _assess(flow_score=50.0, analyst_buy_pct=1.0, analyst_upside_pct=30.0)
    bd = sa.assessment.breakdown_dict
    assert bd["analyst_consensus"] == 100.0
    assert sa.assessment.score > 50


def test_signal_seasonality_tailwind_uses_win_rate():
    # is_tailwind (avg>0 and win>50) → component = win_rate_pct = 80.0
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
    # All 3 optional present → max_range=12; broad_score near top
    # If broad_score=12 (max), normalized = (12+12)/(2*12)*100 = 100
    sa = _assess(flow_score=50.0, bandar_broad_score=10, bandar_max_range=12)
    bd = sa.assessment.breakdown_dict
    assert bd["bandar_intensity"] > 85.0


def test_signal_strong_when_multiple_factors_elevated():
    # score=91.7 → foreign=91.7; insider=+1.0 → 100; analyst all-buy → 100; seasonality tailwind 75%
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


# ─── Behavioral parity: screener integration ─────────────────────────────────


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
    # Canonical key present
    assert "coverage_score" in sa_dict
    # Legacy key preserved for backward compat
    assert "confidence_score" in sa_dict
    # Both carry the same value
    assert sa_dict["coverage_score"] == sa_dict["confidence_score"]
    assert sa_dict["coverage_score"] is not None


# ── Piotroski quality gate ────────────────────────────────────────────────────


def _make_use_case_with_fundamentals(piotroski_score: int | None):
    """Build a use case with a fundamentals_provider stub returning the given F-Score."""
    from unittest.mock import MagicMock

    from src.domain.value_objects.company_fundamentals import CompanyFundamentals

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), _Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, _Decimal("110")) for day in session_dates]

    fund_prov = MagicMock()
    if piotroski_score is not None:
        fund_prov.get_fundamentals.return_value = CompanyFundamentals(
            ticker="BBCA",
            pe_ratio_ttm=12.0,
            roe_ttm=15.0,
            net_profit_margin=12.0,
            revenue_yoy_growth=8.0,
            piotroski_f_score=piotroski_score,
            dividend_yield=2.0,
            week52_high=1200.0,
            week52_low=800.0,
            near_52w_high_rank=50.0,
        )
    else:
        fund_prov.get_fundamentals.return_value = None

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        fundamentals_provider=fund_prov,
    )
    return use_case, as_of


def test_min_piotroski_zero_does_not_filter():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=3)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=0,
        )
    )
    assert len(response.candidates) == 1


def test_min_piotroski_excludes_below_threshold():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=3)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=5,
        )
    )
    assert len(response.candidates) == 0


def test_min_piotroski_includes_at_threshold():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=5)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=5,
        )
    )
    assert len(response.candidates) == 1


def test_min_piotroski_excludes_when_no_fundamentals():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=None)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=4,
        )
    )
    assert len(response.candidates) == 0


def test_min_piotroski_passes_when_no_fundamentals_and_gate_disabled():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=None)
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=0,
        )
    )
    assert len(response.candidates) == 1


# ── Early-pruning gate tests ──────────────────────────────────────────────────
# Verify that enrichment providers are NOT queried for tickers that fail the
# market_cap or piotroski gates (Rec 13: early market_cap floor pruning).


def _make_use_case_with_all_providers(
    market_cap_idr: int | None,
    piotroski_score: int | None,
    *,
    candidate_observations_repository=None,
):
    """Build a use case with all enrichment providers mocked so we can assert call counts."""
    from unittest.mock import MagicMock

    from src.domain.value_objects.company_fundamentals import CompanyFundamentals

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), _Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, _Decimal("110")) for day in session_dates]

    fund_prov = MagicMock()
    fund_prov.get_fundamentals.return_value = (
        CompanyFundamentals(
            ticker="BBCA",
            pe_ratio_ttm=12.0,
            roe_ttm=15.0,
            net_profit_margin=12.0,
            revenue_yoy_growth=8.0,
            piotroski_f_score=piotroski_score,
            dividend_yield=2.0,
            week52_high=1200.0,
            week52_low=800.0,
            near_52w_high_rank=50.0,
            market_cap_idr=market_cap_idr,
        )
        if piotroski_score is not None or market_cap_idr is not None
        else None
    )

    seasonality_prov = MagicMock()
    seasonality_prov.get_seasonal_edge.return_value = None
    bandar_prov = MagicMock()
    bandar_prov.get_snapshot.return_value = None
    analyst_prov = MagicMock()
    analyst_prov.get_consensus.return_value = None

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        fundamentals_provider=fund_prov,
        seasonality_provider=seasonality_prov,
        bandar_detector_provider=bandar_prov,
        analyst_consensus_provider=analyst_prov,
        candidate_observations_repository=candidate_observations_repository,
    )
    return use_case, as_of, fund_prov, seasonality_prov, bandar_prov, analyst_prov


def test_market_cap_floor_excludes_below_threshold():
    use_case, as_of, fund_prov, *_ = _make_use_case_with_all_providers(
        market_cap_idr=500_000_000_000,
        piotroski_score=8,  # 500B IDR < 1T floor
    )
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_market_cap_idr=1_000_000_000_000,
        )
    )
    assert len(response.candidates) == 0
    assert response.tickers_skipped == 1


def test_market_cap_floor_includes_at_or_above_threshold():
    use_case, as_of, *_ = _make_use_case_with_all_providers(
        market_cap_idr=2_000_000_000_000,
        piotroski_score=8,  # 2T IDR >= 1T floor
    )
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_market_cap_idr=1_000_000_000_000,
        )
    )
    assert len(response.candidates) == 1


def test_market_cap_floor_skips_enrichment_for_rejected_ticker():
    """Enrichment providers must NOT be called when market cap gate rejects the ticker."""
    use_case, as_of, fund_prov, seasonality_prov, bandar_prov, analyst_prov = (
        _make_use_case_with_all_providers(
            market_cap_idr=100_000_000_000,
            piotroski_score=8,  # 100B IDR < 1T floor
        )
    )
    use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_market_cap_idr=1_000_000_000_000,
        )
    )
    # Fundamentals fetched once for the gate check
    fund_prov.get_fundamentals.assert_called_once()
    # All other enrichment skipped
    seasonality_prov.get_seasonal_edge.assert_not_called()
    bandar_prov.get_snapshot.assert_not_called()
    analyst_prov.get_consensus.assert_not_called()


def test_piotroski_gate_skips_enrichment_for_rejected_ticker():
    """Enrichment providers must NOT be called when piotroski gate rejects the ticker."""
    use_case, as_of, fund_prov, seasonality_prov, bandar_prov, analyst_prov = (
        _make_use_case_with_all_providers(
            market_cap_idr=5_000_000_000_000,
            piotroski_score=2,  # f-score 2 < floor 5
        )
    )
    use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_piotroski=5,
        )
    )
    fund_prov.get_fundamentals.assert_called_once()
    seasonality_prov.get_seasonal_edge.assert_not_called()
    bandar_prov.get_snapshot.assert_not_called()
    analyst_prov.get_consensus.assert_not_called()


def test_no_gate_active_fundamentals_fetched_in_enrichment_pass():
    """When no gate is active, fundamentals are fetched once in the normal enrichment pass."""
    use_case, as_of, fund_prov, *_ = _make_use_case_with_all_providers(
        market_cap_idr=5_000_000_000_000,
        piotroski_score=8,
    )
    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            # No gate — min_market_cap_idr=0 and min_piotroski=0 (defaults)
        )
    )
    assert len(response.candidates) == 1
    # Fundamentals still fetched exactly once (in enrichment pass, not gate pass)
    fund_prov.get_fundamentals.assert_called_once()


# ---------------------------------------------------------------------------
# classify_multi_window_pattern
# ---------------------------------------------------------------------------

from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
    classify_multi_window_pattern,
)


def _make_candidate(score: float, bb_width_pctile: float | None = None) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker="TEST",
        window_days=7,
        net_buy_days=4,
        total_days=5,
        net_buy_ratio=0.8,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1000"),
        current_price=Decimal("1000"),
        vwap_discount_pct=0.0,
        rsi=50.0,
        trend="UP",
        foreign_flow_score=score,
        top_brokers=None,
        institutional_flag=False,
        bb_width_pctile=bb_width_pctile,
    )


_WINDOWS = [7, 30, 90]
_MIN_SCORE = 60.0
_BB_PCTILE = 0.20


def test_classify_all_windows_hot_is_sustained():
    candidates = {w: _make_candidate(score=70.0) for w in _WINDOWS}
    assert (
        classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "sustained"
    )


def test_classify_only_short_window_hot_is_fresh_rotation():
    candidates = {
        7: _make_candidate(score=70.0),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=40.0),
    }
    assert (
        classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE)
        == "fresh rotation"
    )


def test_classify_only_long_window_hot_is_long_term_only():
    candidates = {
        7: _make_candidate(score=40.0),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=70.0),
    }
    assert (
        classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE)
        == "long-term only"
    )


def test_classify_short_and_long_hot_but_not_all_is_building():
    # "building" fires when min hot AND max hot but not all windows hot.
    # If max is NOT hot, "fresh rotation" takes priority (checked first).
    windows = [7, 30, 90, 180]
    candidates = {
        7: _make_candidate(score=70.0),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=40.0),
        180: _make_candidate(score=70.0),
    }
    assert classify_multi_window_pattern(windows, candidates, _MIN_SCORE, _BB_PCTILE) == "building"


def test_classify_coiled_spring_when_squeeze_and_high_score():
    candidates = {
        7: _make_candidate(score=70.0, bb_width_pctile=0.10),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=40.0),
    }
    assert (
        classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE)
        == "coiled spring"
    )


def test_classify_weak_when_no_windows_hot():
    candidates = {w: _make_candidate(score=30.0) for w in _WINDOWS}
    assert classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "weak"


# ── Phase 7: persistence wiring ───────────────────────────────────────────────


class SpyCandidateObservationsRepository:
    """Records save_many calls for assertion."""

    def __init__(self):
        self.saved: list = []
        self.raise_on_save: Exception | None = None

    def save_many(self, observations):
        if self.raise_on_save is not None:
            raise self.raise_on_save
        self.saved.extend(observations)

    def get_latest(self, ticker, snapshot_date):
        return None

    def list_recent(self, ticker, *, before_date=None, limit=20):
        return []


def test_screen_persists_candidate_observations_when_repo_injected():
    """When candidate_observations_repository is injected, save_many receives
    correctly-shaped observations for each passing candidate."""
    from src.domain.ports.candidate_observations_repository import CandidateObservation

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        candidate_observations_repository=spy_repo,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    assert obs.ticker == "BBCA"
    assert obs.snapshot_date == as_of

    payload = obs.payload
    assert payload["schema_version"] == 1
    assert payload["artifact_type"] == "candidate_observation"
    assert payload["ticker"] == "BBCA"
    assert payload["screen_result"] == "pass"
    fingerprint = payload["sub_signal_fingerprint"]
    assert fingerprint["rsi_at_signal"] is not None
    assert fingerprint["cnfb_20d_at_signal"] is not None
    assert fingerprint["coverage_score"] == 0.5
    assert fingerprint["conviction_score"] is not None
    assert fingerprint["coverage_score"] != fingerprint["conviction_score"]
    assert fingerprint["setup_phase_current"] is not None
    assert fingerprint["phase_coverage_score"] is not None
    assert fingerprint["phase_conviction_score"] is not None
    assert fingerprint["tp_market_cap_bucket"] == "UNKNOWN"
    assert "phase_history" in fingerprint
    # flow_evidence key must be present inside signal (None when no signal engine;
    # the key itself must exist so replay consumers don't need to special-case)
    assert "flow_evidence" in (payload.get("signal") or {})
    # setup_name forward-compat key: the batch screener never evaluates a named
    # setup, so DecisionConstraints has no setup_name field and this is always
    # None today. The key itself must be present in the fingerprint dict.
    assert "setup_name" in fingerprint
    assert fingerprint["setup_name"] is None


def test_screen_persists_setup_family_fingerprint_when_swing_setup_catalog_matches():
    """When a swing_setup_catalog is injected and the screened candidate's
    derived signals MATCH a named setup (coiled-spring, family "breakout"),
    the persisted sub_signal_fingerprint carries the resolved setup-family
    fields end-to-end (screen -> PrimarySetupFamilyResolver -> payload)."""
    from src.application.use_case.evaluate_swing_setup_use_case import (
        CoiledSpringSetupConfig,
        ForeignBounceSetupConfig,
        PullbackContinuationSetupConfig,
        SmartMoneyConfirmedSetupConfig,
        SwingSetupCatalogConfig,
    )
    from src.domain.ports.candidate_observations_repository import CandidateObservation

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    # 130 days of varied-close candles: bb_width_pctile is None unless the use
    # case can compute >= bb_history (60) rolling BB widths (period 20), which
    # in turn needs a long enough, non-constant-price candle history. Without
    # this, even a maximally loosened coiled-spring config would fail the
    # "bb_width_pctile present" gate and only ever PARTIAL-match.
    candles = [
        _candle("BBCA", date(2025, 9, 1) + timedelta(days=i), Decimal("100") + Decimal(i % 5))
        for i in range(130)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    # coiled-spring gates are maximally loosened so the screened candidate's
    # derived signals MATCH regardless of the exact computed values (we don't
    # control AccumulationCandidate fields directly here, unlike the resolver
    # unit tests). The other three setups are disabled so they cannot also
    # match and confuse the "primary family" assertion.
    swing_setup_catalog = SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(enabled=False, family="foreign_bounce"),
        coiled_spring=CoiledSpringSetupConfig(
            gate_min_foreign_flow_score=0.0,
            gate_max_bb_width_pctile=1.0,
            gate_min_flow_ratio_pct=-100.0,
            gate_max_rsi=100.0,
            family="breakout",
        ),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=False, family="confirmation"
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            enabled=False, family="pullback"
        ),
    )

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        candidate_observations_repository=spy_repo,
        swing_setup_catalog=swing_setup_catalog,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]
    assert "matched_setup_families" in fingerprint
    assert "primary_setup_family" in fingerprint
    assert "setup_family_source" in fingerprint
    assert "setup_family_rationale" in fingerprint
    assert fingerprint["primary_setup_family"] == "breakout"
    assert "breakout" in fingerprint["matched_setup_families"]


def test_screen_persists_market_cap_bucket_when_fundamentals_available():
    from src.domain.ports.candidate_observations_repository import CandidateObservation

    spy_repo = SpyCandidateObservationsRepository()
    use_case, as_of, *_ = _make_use_case_with_all_providers(
        market_cap_idr=15_000_000_000_000,
        piotroski_score=8,
        candidate_observations_repository=spy_repo,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1
    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]
    assert fingerprint["tp_market_cap_bucket"] == "large"


def test_screen_persists_sector_context_fingerprint_when_builder_available(monkeypatch):
    class FakeSectorContextBuilder:
        def peers_for_ticker(self, ticker):
            return ("BBRI",)

        def build(self, request):
            return SectorContextEvidence(
                sector="banking",
                peer_count=1,
                peer_tickers=("BBRI",),
                sector_20d_return=0.02,
                sector_vs_ihsg_20d=0.01,
                sector_breadth=1.0,
                ticker_vs_sector_rs=0.01,
                sector_regime="BULLISH",
                coverage_score=1.0,
                evidence_status=EvidenceStatus.DIAGNOSTIC,
                reasons=(),
                unavailable_reasons=(),
            )

    monkeypatch.setattr(
        "src.application.services.sector_context_evidence_builder."
        "SectorContextEvidenceBuilder.from_yaml",
        staticmethod(lambda: FakeSectorContextBuilder()),
    )
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ] + [
        _candle("IHSG", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        candidate_observations_repository=spy_repo,
    )

    use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    fingerprint = spy_repo.saved[0].payload["sub_signal_fingerprint"]
    assert fingerprint["sc_sector"] == "banking"
    assert fingerprint["sc_sector_regime"] == "BULLISH"
    assert fingerprint["sc_sector_vs_ihsg_20d"] == pytest.approx(0.01)


def test_screen_persists_rejected_candidates_with_filter_outcome():
    """Candidates rejected by min_foreign_flow_score are still persisted as
    negative samples for future tuning."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        candidate_observations_repository=spy_repo,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            min_foreign_flow_score=9999.0,  # impossible threshold — all rejected
            min_foreign_flow_score_enabled=True,
        )
    )

    # No survivors — rejected by flow score threshold
    assert len(response.candidates) == 0
    # Rejected candidate still persisted as a learnable negative sample
    assert len(spy_repo.saved) == 1
    payload = spy_repo.saved[0].payload
    assert payload["screen_result"] == "rejected_flow"
    assert payload["ticker"] == "BBCA"
    assert payload["schema_version"] == 1


def test_screen_result_returned_even_when_persistence_fails():
    """save_many failure must not block the screen response (best-effort persistence)."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    spy_repo.raise_on_save = RuntimeError("DB write failed")

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        candidate_observations_repository=spy_repo,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    # Response returned despite persistence failure
    assert len(response.candidates) == 1
    assert response.candidates[0].ticker == "BBCA"


def test_screen_populates_setup_phase_for_displayed_candidates():
    """Displayed screen candidates get setup_phase populated, not only persisted
    observations — no candidate_observations_repository is injected here."""
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot

    candidate = response.candidates[0]
    assert candidate.setup_phase is not None
    assert isinstance(candidate.setup_phase, SetupPhaseSnapshot)
    assert candidate.to_dict()["setup_phase"] == candidate.setup_phase.to_dict()


def test_screen_setup_phase_is_none_when_detection_fails(monkeypatch):
    """A detection failure must not crash the screen; setup_phase falls back to None."""
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    def _boom(self, **kwargs):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(
        "src.application.services.setup_phase_detector.SetupPhaseDetector.detect",
        _boom,
    )

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert len(response.candidates) == 1
    assert response.candidates[0].setup_phase is None
    assert response.candidates[0].to_dict()["setup_phase"] is None


def test_screen_recomputes_setup_phase_when_stage2_family_differs_from_preliminary():
    """Regression test for the stage-1/stage-2 setup-family inconsistency fix
    in _persist_candidate_observations.

    Stage 1 (main loop, _detect_candidate_setup_phase with no strategy_evidence
    yet) resolves a *preliminary* setup family and detects setup_phase against
    it. Stage 2 (_persist_candidate_observations, after strategy_evidence is
    built) re-resolves the *final* family via self._setup_family_resolver — a
    higher-priority source (strategy_evidence) can revise the family. Before
    the fix, the persisted setup_phase fields (e.g. phase_sequence_valid)
    would still reflect the stale stage-1 family's sequencing rules even
    though primary_setup_family in the payload reflects the new stage-2
    family. The fix recomputes setup_phase when
    setup_family_result.primary_setup_family != preliminary_family.

    We inject a fake PrimarySetupFamilyResolver that returns "breakout" when
    called without strategy_evidence (stage 1: _resolve_preliminary_setup_family
    and _detect_candidate_setup_phase's internal default path never pass
    strategy_evidence) and "foreign_bounce" when called with strategy_evidence
    (stage 2's full resolve call in _persist_candidate_observations always
    passes strategy_evidence=strategy_evidence). Setting request.strategy_name
    to a bogus (non-existent) strategy name is enough to make
    _build_candidate_strategy_evidence produce a real, non-None
    StrategyEvidence object: StrategyEvidenceBuilder.build() wraps the
    strategy-loading and rule-evaluation logic in a broad try/except that
    falls back to _unavailable(...), which still constructs and returns a
    genuine StrategyEvidence instance (not None) -- confirmed by reading
    src/application/services/strategy_evidence_builder.py.

    Candle data is the same 130-day varied-close recipe used in
    test_screen_persists_setup_family_fingerprint_when_swing_setup_catalog_matches
    to produce a real (non-None) bb_width_pctile <= 0.20, landing the
    genuinely-derived setup_phase in SetupPhaseState.COMPRESSION.

    Per SetupPhaseConfig's default requirements_by_family:
      - "breakout"       -> sequence (COMPRESSION, BREAKOUT_CONFIRMATION).
                            COMPRESSION is idx=0 -> sequence_valid=True
                            (first phase in sequence, no prior history needed).
      - "foreign_bounce" -> same sequence object as "accumulation":
                            (ACCUMULATION, COMPRESSION, BREAKOUT_CONFIRMATION).
                            COMPRESSION is idx=1 -> requires ACCUMULATION to
                            already be in previous_phases, which it is not
                            (no observation history seeded) -> sequence_valid=False.

    So: if the fix's recompute reran phase detection with the FINAL family
    ("foreign_bounce"), the persisted phase_sequence_valid must be False. If
    the stale stage-1 family ("breakout") were used instead (the bug), it
    would incorrectly be True. This test asserts False, proving the recompute
    used the FINAL family.
    """
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )
    from src.domain.ports.candidate_observations_repository import CandidateObservation

    class _FakeResolver:
        """Returns a different primary_setup_family depending on whether
        strategy_evidence is present, simulating a higher-priority source
        (strategy_evidence) revising the family between stage 1 and stage 2."""

        def resolve(self, *, candidate, strategy_evidence=None, **kwargs):
            if strategy_evidence is None:
                # Stage 1: _resolve_preliminary_setup_family and
                # _detect_candidate_setup_phase's internal default path.
                return PrimarySetupFamilyResult(
                    matched_setup_families=("breakout",),
                    primary_setup_family="breakout",
                    setup_family_source="detected_screen_evidence",
                )
            # Stage 2: _persist_candidate_observations' full resolve call.
            return PrimarySetupFamilyResult(
                matched_setup_families=("foreign_bounce", "breakout"),
                primary_setup_family="foreign_bounce",
                setup_family_source="strategy_evidence",
            )

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    # 130 days of varied-close candles so bb_width_pctile is a real, non-None
    # value (needs >= bb_history=60 rolling BB widths over period 20, which in
    # turn needs a long enough, non-constant-price candle history) -- same
    # technique as the neighboring swing-setup-catalog fingerprint test, but
    # with modulo 6 (instead of 5) so the naturally-derived phase actually
    # lands in SetupPhaseState.COMPRESSION (bb_width_pctile ~0.167 <= the
    # default 0.20 threshold) rather than ACCUMULATION -- verified empirically,
    # since _constructive_phase() checks the compression gate before the
    # accumulation gate but only when bb_width_pctile is low enough.
    candles = [
        _candle("BBCA", date(2025, 9, 1) + timedelta(days=i), Decimal("100") + Decimal(i % 6))
        for i in range(130)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        candidate_observations_repository=spy_repo,
        primary_setup_family_resolver=_FakeResolver(),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            # Non-None (even if not a real/loadable strategy YAML) is enough to
            # make _build_candidate_strategy_evidence pass strategy_evidence
            # through to stage 2's resolve() call as non-None.
            strategy_name="nonexistent-strategy-for-regression-test",
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]

    # The persisted family must be the FINAL (stage-2) family, not the stale
    # stage-1 preliminary one.
    assert fingerprint["primary_setup_family"] == "foreign_bounce"
    assert fingerprint["setup_family_source"] == "strategy_evidence"

    # Sanity check: the underlying candle-derived phase actually landed on
    # COMPRESSION as designed -- otherwise the sequence_valid assertion below
    # would be vacuous.
    assert fingerprint["setup_phase_current"] == "COMPRESSION"

    # The crux of the regression test: phase_sequence_valid must reflect the
    # FINAL family's ("foreign_bounce") sequencing rule (requires prior
    # ACCUMULATION phase, absent here -> False), not the stale preliminary
    # family's ("breakout") rule (COMPRESSION is first in sequence -> True).
    # If the recompute branch were missing/broken, this would incorrectly be
    # True.
    assert fingerprint["phase_sequence_valid"] is False


def test_screen_persists_relative_strength_and_evaluates_rs_policy():
    """RS vs IHSG flows end-to-end: RelativeStrengthCalculator computes real
    values from BBCA + IHSG candles seeded in the same MockMarketRepository,
    the raw values are persisted in sub_signal_fingerprint
    (rs_vs_ihsg_20d_at_signal / rs_vs_ihsg_5d_at_signal), and the 5d value
    flows through SetupEvidenceBuilder/SetupPhaseDetector far enough that the
    RS policy (keyed by setup family) is genuinely evaluated rather than
    short-circuiting on "no policy for this family" / "no RS available".

    Uses a 2026 as_of_date so SetupEvidenceBuilder's own freshness gate
    (_IHSG_AVAILABLE_FROM = 2025-07-01) does not force rs_vs_ihsg_5d back to
    None before SetupPhaseDetector sees it.

    A loosened coiled-spring swing_setup_catalog (family="breakout") is
    injected -- same technique as
    test_screen_persists_setup_family_fingerprint_when_swing_setup_catalog_matches
    -- so the candidate resolves to setup_family="breakout", for which
    SetupPhaseConfig's default rs_policy_by_setup_family has a real entry,
    making cfg.rs_policy_for("breakout") non-None.
    """
    from src.application.use_case.evaluate_swing_setup_use_case import (
        CoiledSpringSetupConfig,
        ForeignBounceSetupConfig,
        PullbackContinuationSetupConfig,
        SmartMoneyConfirmedSetupConfig,
        SwingSetupCatalogConfig,
    )
    from src.domain.ports.candidate_observations_repository import CandidateObservation

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]

    # 130 days of varied (non-flat), rising-faster-than-benchmark closes for
    # both BBCA and IHSG so a real, non-None RS is computed for both windows.
    # Same 130-day / bb_width_pctile technique as the neighboring
    # swing-setup-catalog fingerprint test.
    base_dates = [date(2025, 9, 1) + timedelta(days=i) for i in range(130)]
    bbca_candles = [
        _candle("BBCA", d, Decimal("100") + Decimal(i % 5) + Decimal(i) * Decimal("0.05"))
        for i, d in enumerate(base_dates)
    ]
    ihsg_candles = [
        _candle("IHSG", d, Decimal("100") + Decimal(i) * Decimal("0.01"))
        for i, d in enumerate(base_dates)
    ]
    candles = bbca_candles + ihsg_candles
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    # coiled-spring gates maximally loosened, other setups disabled -- exactly
    # the pattern used in
    # test_screen_persists_setup_family_fingerprint_when_swing_setup_catalog_matches.
    swing_setup_catalog = SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(enabled=False, family="foreign_bounce"),
        coiled_spring=CoiledSpringSetupConfig(
            gate_min_foreign_flow_score=0.0,
            gate_max_bb_width_pctile=1.0,
            gate_min_flow_ratio_pct=-100.0,
            gate_max_rsi=100.0,
            family="breakout",
        ),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=False, family="confirmation"
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            enabled=False, family="pullback"
        ),
    )

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        candidate_observations_repository=spy_repo,
        swing_setup_catalog=swing_setup_catalog,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]

    assert fingerprint["rs_vs_ihsg_20d_at_signal"] is not None
    assert fingerprint["rs_vs_ihsg_5d_at_signal"] is not None
    assert "rs_policy_unavailable" not in fingerprint["phase_reasons"]
    assert any(
        reason == "rs_policy_passed" or reason.startswith("rs_policy_warning")
        or reason.startswith("rs_policy_hard_exclude")
        for reason in fingerprint["phase_reasons"]
    )


def test_screen_rs_fields_stay_none_when_ihsg_candles_missing():
    """Regression: when no IHSG candles exist at all in the market repository,
    RelativeStrengthCalculator resolves both windows to None (insufficient
    benchmark candles) rather than raising, and the screen still completes
    normally with the RS fingerprint fields set to None."""
    from src.domain.ports.candidate_observations_repository import CandidateObservation

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),  # no IHSG candles seeded
        candidate_observations_repository=spy_repo,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]
    assert fingerprint["rs_vs_ihsg_20d_at_signal"] is None
    assert fingerprint["rs_vs_ihsg_5d_at_signal"] is None
