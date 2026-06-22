"""Tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.use_case.accumulation_screen import (
    BCI_CLUSTER,
    BCI_RETAIL,
    BCI_STABLE,
    TIER1_FOREIGN_BROKERS,
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.ticker_notation import TickerNotation, TickerNotationSnapshot


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
    assert c.score_breakdown["inst"] == 15.0


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
    assert c.score_breakdown["inst"] == 5.0


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
    assert c.score_breakdown["inst"] == 0.0


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
    assert c.score_breakdown["inst"] == 0.0


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
    def get_notation(self, ticker: str) -> TickerNotationSnapshot | None:
        return TickerNotationSnapshot(
            ticker=ticker.upper(),
            status="STATUS_ACTIVE",
            listing_board="Papan Pemantauan Khusus",
            haircut_percentage="100%",
            notations=[TickerNotation(code="X", description="Special monitoring")],
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
    assert enriched.candidates[0].score == base.candidates[0].score
    assert enriched.candidates[0].to_dict()["ticker_notation"]["notations"][0]["code"] == "X"


# ─── Composite Signal Score ─────────────────────────────────────────────────

from datetime import date as _date
from decimal import Decimal as _Decimal

from src.application.use_case.accumulation_screen import _composite_score
from src.domain.value_objects.analyst_consensus import AnalystConsensus
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.domain.value_objects.forward_estimates import ForwardEstimates
from src.domain.value_objects.seasonal_edge import SeasonalEdge


def _minimal_candidate(score: float = 80.0) -> "AccumulationCandidate":
    from src.application.use_case.accumulation_screen import AccumulationCandidate
    return AccumulationCandidate(
        ticker="TEST",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=5 / 7,
        total_net_value=_Decimal("1_000_000_000"),
        consecutive_streak=5,
        foreign_vwap=_Decimal("1000"),
        current_price=_Decimal("950"),
        vwap_discount_pct=5.0,
        rsi=42.0,
        trend="UP",
        score=score,
        top_brokers=["ZP", "AK"],
        institutional_flag=True,
    )


def test_composite_score_all_neutral_when_no_enrichment():
    c = _minimal_candidate(score=60.0)
    cs = _composite_score(c)
    # With no enrichment data: bandar=50, piotroski=50, seasonality=50, analyst=50, fwd=50
    # Only foreign_flow from score=60 → 60/120*100=50.0
    # Total = 0.20*50 + 0.20*50 + 0.20*50 + 0.15*50 + 0.15*50 + 0.10*50 = 50.0
    assert cs.total == 50.0
    assert not cs.has_bandar
    assert not cs.has_piotroski
    assert not cs.has_seasonality
    assert not cs.has_analyst
    assert not cs.has_forward_eps


def test_composite_score_piotroski_8_raises_score():
    c = _minimal_candidate(score=60.0)
    c.fundamentals = CompanyFundamentals(
        ticker="TEST", pe_ratio_ttm=12.0, roe_ttm=18.0, net_profit_margin=15.0,
        revenue_yoy_growth=10.0, piotroski_f_score=8, dividend_yield=2.0,
        week52_high=1200.0, week52_low=800.0, near_52w_high_rank=70.0,
    )
    cs = _composite_score(c)
    # piotroski_component = 8/9*100 = 88.9
    assert cs.has_piotroski
    assert abs(cs.piotroski - 88.9) < 0.5
    assert cs.total > 50.0


def test_composite_score_analyst_all_buy_full_upside():
    c = _minimal_candidate(score=60.0)
    c.analyst_consensus = AnalystConsensus(
        ticker="TEST", buy_count=5, hold_count=0, sell_count=0,
        avg_price_target=1300.0, current_price=1000.0, last_updated=_date.today(),
    )
    cs = _composite_score(c)
    # buy_pct=100% → buy_score=60; upside=30% → upside_score=40; total=100
    assert cs.has_analyst
    assert cs.analyst == 100.0
    assert cs.total > 50.0


def test_composite_score_seasonality_tailwind_uses_win_rate():
    c = _minimal_candidate(score=60.0)
    c.seasonal_edge = SeasonalEdge(
        ticker="TEST", month=6, avg_monthly_return_pct=2.5,
        win_rate_pct=80.0, positive_years=4, total_years=5, back_years=5,
    )
    cs = _composite_score(c)
    assert cs.has_seasonality
    assert cs.seasonality == 80.0  # is_tailwind → win_rate_pct directly


def test_composite_score_bandar_full_accumulation():
    c = _minimal_candidate(score=60.0)
    c.bandar_detector = BandarDetectorSnapshot(
        ticker="TEST", session_date=_date.today(),
        broker_accdist="Acc", today_accdist="Big Acc", five_day_accdist="Big Acc",
        top1_accdist="Big Acc", top1_percent=65.0, today_percent=12.0,
        total_buyer=8, total_seller=3,
        top3_accdist="Big Acc", top5_accdist="Small Acc", top10_accdist="Small Acc",
    )
    cs = _composite_score(c)
    assert cs.has_bandar
    assert cs.bandar > 85.0  # all signals positive → near top of range


def test_composite_high_conviction_requires_four_above_60():
    c = _minimal_candidate(score=110.0)  # foreign_flow = 91.7
    c.fundamentals = CompanyFundamentals(
        ticker="TEST", pe_ratio_ttm=10.0, roe_ttm=22.0, net_profit_margin=18.0,
        revenue_yoy_growth=15.0, piotroski_f_score=9, dividend_yield=2.0,
        week52_high=1200.0, week52_low=800.0, near_52w_high_rank=70.0,
    )
    c.analyst_consensus = AnalystConsensus(
        ticker="TEST", buy_count=4, hold_count=1, sell_count=0,
        avg_price_target=1200.0, current_price=1000.0, last_updated=_date.today(),
    )
    c.seasonal_edge = SeasonalEdge(
        ticker="TEST", month=6, avg_monthly_return_pct=1.5,
        win_rate_pct=75.0, positive_years=3, total_years=4, back_years=5,
    )
    c.bandar_detector = BandarDetectorSnapshot(
        ticker="TEST", session_date=_date.today(),
        broker_accdist="Acc", today_accdist="Big Acc", five_day_accdist="Small Acc",
        top1_accdist="Big Acc", top1_percent=55.0, today_percent=10.0,
        total_buyer=6, total_seller=2,
    )
    cs = _composite_score(c)
    assert cs.is_high_conviction
    assert cs.total > 70.0


# ── Piotroski quality gate ────────────────────────────────────────────────────

def _make_use_case_with_fundamentals(piotroski_score: int | None):
    """Build a use case with a fundamentals_provider stub returning the given F-Score."""
    from unittest.mock import MagicMock
    from src.domain.value_objects.company_fundamentals import CompanyFundamentals

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [_candle("BBCA", date(2025, 12, 1) + timedelta(days=i), _Decimal("100")) for i in range(45)]
    summaries = [_summary("BBCA", day, _Decimal("110")) for day in session_dates]

    fund_prov = MagicMock()
    if piotroski_score is not None:
        fund_prov.get_fundamentals.return_value = CompanyFundamentals(
            ticker="BBCA", pe_ratio_ttm=12.0, roe_ttm=15.0, net_profit_margin=12.0,
            revenue_yoy_growth=8.0, piotroski_f_score=piotroski_score,
            dividend_yield=2.0, week52_high=1200.0, week52_low=800.0,
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
    response = use_case.execute(AccumulationScreenRequest(
        tickers=["BBCA"], window_days=7, min_net_buy_days=1,
        as_of_date=as_of, min_piotroski=0,
    ))
    assert len(response.candidates) == 1


def test_min_piotroski_excludes_below_threshold():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=3)
    response = use_case.execute(AccumulationScreenRequest(
        tickers=["BBCA"], window_days=7, min_net_buy_days=1,
        as_of_date=as_of, min_piotroski=5,
    ))
    assert len(response.candidates) == 0


def test_min_piotroski_includes_at_threshold():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=5)
    response = use_case.execute(AccumulationScreenRequest(
        tickers=["BBCA"], window_days=7, min_net_buy_days=1,
        as_of_date=as_of, min_piotroski=5,
    ))
    assert len(response.candidates) == 1


def test_min_piotroski_excludes_when_no_fundamentals():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=None)
    response = use_case.execute(AccumulationScreenRequest(
        tickers=["BBCA"], window_days=7, min_net_buy_days=1,
        as_of_date=as_of, min_piotroski=4,
    ))
    assert len(response.candidates) == 0


def test_min_piotroski_passes_when_no_fundamentals_and_gate_disabled():
    use_case, as_of = _make_use_case_with_fundamentals(piotroski_score=None)
    response = use_case.execute(AccumulationScreenRequest(
        tickers=["BBCA"], window_days=7, min_net_buy_days=1,
        as_of_date=as_of, min_piotroski=0,
    ))
    assert len(response.candidates) == 1


# ---------------------------------------------------------------------------
# classify_multi_window_pattern
# ---------------------------------------------------------------------------

from src.application.use_case.accumulation_screen import (
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
        score=score,
        top_brokers=None,
        institutional_flag=False,
        bb_width_pctile=bb_width_pctile,
    )


_WINDOWS = [7, 30, 90]
_MIN_SCORE = 60.0
_BB_PCTILE = 0.20


def test_classify_all_windows_hot_is_sustained():
    candidates = {w: _make_candidate(score=70.0) for w in _WINDOWS}
    assert classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "sustained"


def test_classify_only_short_window_hot_is_fresh_rotation():
    candidates = {
        7: _make_candidate(score=70.0),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=40.0),
    }
    assert classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "fresh rotation"


def test_classify_only_long_window_hot_is_long_term_only():
    candidates = {
        7: _make_candidate(score=40.0),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=70.0),
    }
    assert classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "long-term only"


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
    assert classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "coiled spring"


def test_classify_weak_when_no_windows_hot():
    candidates = {w: _make_candidate(score=30.0) for w in _WINDOWS}
    assert classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "weak"
