"""
Tests for historical accumulation audit.

The audit must be deterministic, offline, and free from future data leakage.
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.services.stats import pct_change as _pct_change
from src.application.use_case.accumulation_audit_use_case import (
    AccumulationAuditPolicy,
    AccumulationAuditRequest,
    AccumulationAuditUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from tests.application.use_case.accumulation_screen_fixtures import FakeRulesLoader


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
        candles = self.get_candles(ticker)
        if not candles:
            return None
        return candles[0].date, candles[-1].date

    def list_tickers_with_candles_between(self, start_date, end_date):
        return []


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


def test_accumulation_audit_pct_change_zero_base_is_zero():
    assert _pct_change(Decimal("100"), Decimal("0")) == 0.0


def _candle(ticker: str, day: date, close: Decimal) -> Candle:
    return _ohlc(ticker, day, close, close, close, close)


def _ohlc(
    ticker: str,
    day: date,
    open_price: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1_000_000,
    )


def _summary(ticker: str, day: date, close: Decimal) -> BrokerSummary:
    buy_lot = 10_000
    buy_value = close * Decimal(buy_lot * 100)
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


def _tx(
    code: str,
    buy: str,
    sell: str,
    broker_type: BrokerType = BrokerType.FOREIGN,
) -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=code,
        broker_type=broker_type,
        buy_lot=1000,
        sell_lot=500,
        buy_value=Decimal(buy),
        sell_value=Decimal(sell),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
    )


def _summary_with_brokers(
    ticker: str,
    day: date,
    close: Decimal,
    top_buyers: tuple[BrokerTransaction, ...] = (),
    top_sellers: tuple[BrokerTransaction, ...] = (),
) -> BrokerSummary:
    base = _summary(ticker, day, close)
    return BrokerSummary(
        ticker=base.ticker,
        date=base.date,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=base.foreign_buy_value,
        foreign_sell_value=base.foreign_sell_value,
        foreign_buy_lot=base.foreign_buy_lot,
        foreign_sell_lot=base.foreign_sell_lot,
        total_value=base.total_value,
        total_lot=base.total_lot,
        source="stockbit",
    )


def _alternating_candles(ticker: str, base: date, count: int) -> list[Candle]:
    return [
        _candle(
            ticker,
            base + timedelta(days=i),
            Decimal("100") if i % 2 == 0 else Decimal("101"),
        )
        for i in range(count)
    ]


def test_accumulation_audit_replays_signal_and_forward_returns_without_ai():
    base = date(2026, 1, 1)
    candles = [_candle("BBCA", base + timedelta(days=i), Decimal(100 + i)) for i in range(35)]
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal(100 + i)) for i in range(10, 21)
    ]

    use_case = AccumulationAuditUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=["BBCA"],
            start_date=base + timedelta(days=20),
            end_date=base + timedelta(days=20),
            window_days=7,
            min_net_buy_days=1,
            min_accum_score=0,
            horizon_days=5,
        )
    )

    assert response.total_replay_dates == 1
    assert response.total_records == 1
    record = response.records[0]
    assert record.ticker == "BBCA"
    assert record.current_price == Decimal("120")
    assert record.return_5d_pct == 4.1667
    record_dict = record.to_dict()
    assert record_dict["accum_score"] == record.accum_score
    assert "score" not in record_dict
    assert response.group_stats
    assert response.claim_stamp.evaluation_role == "DESCRIPTIVE"
    assert response.claim_stamp.outcome_basis == "raw_market"
    assert response.claim_stamp.costs_modeled is False
    assert response.skip_ledger.included_records == 1
    assert response.skip_ledger.screen_pass >= 1
    assert record.signal_score is not None


def test_accumulation_audit_does_not_use_future_candle_as_signal_price():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=20)
    candles = [_candle("BBCA", base + timedelta(days=i), Decimal(100 + i)) for i in range(0, 21)]
    candles.extend(
        _candle("BBCA", base + timedelta(days=i), Decimal("1000")) for i in range(21, 28)
    )
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal(100 + i)) for i in range(14, 21)
    ]

    use_case = AccumulationAuditUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=["BBCA"],
            start_date=signal_date,
            end_date=signal_date,
            window_days=7,
            min_net_buy_days=1,
            min_accum_score=0,
            horizon_days=5,
        )
    )

    assert response.records[0].current_price == Decimal("120")
    assert response.records[0].return_5d_pct == 733.3333


def test_accumulation_audit_strict_filters_keep_only_matching_candidates():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    candles = _alternating_candles("BBCA", base, 25)
    candles.extend(_candle("BBCA", base + timedelta(days=i), Decimal("104")) for i in range(25, 31))
    candles.extend(_alternating_candles("BBRI", base, 31))

    summaries = [_summary("BBCA", base + timedelta(days=i), Decimal("110")) for i in range(18, 25)]
    summaries.extend(
        _summary("BBRI", base + timedelta(days=i), Decimal("101")) for i in range(18, 25)
    )

    use_case = AccumulationAuditUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=["BBCA", "BBRI"],
            start_date=signal_date,
            end_date=signal_date,
            window_days=7,
            min_net_buy_days=1,
            min_accum_score=0,
            horizon_days=5,
            min_vwap_disc_pct=5,
            trend="SIDE",
            min_flow_pct=5,
            require_rsi=True,
            max_rsi=60,
        )
    )

    assert [record.ticker for record in response.records] == ["BBCA"]
    assert response.records[0].vwap_disc_pct is not None
    assert response.records[0].vwap_disc_pct >= 5
    assert response.records[0].trend == "SIDE"
    assert response.records[0].flow_pct is not None
    assert response.records[0].flow_pct >= 5
    assert response.records[0].rsi is not None
    assert response.records[0].rsi <= 60
    assert response.skip_ledger.audit_filter_excluded >= 1
    assert (
        response.skip_ledger.audit_filter_excluded
        + response.skip_ledger.skipped_no_forward_data
        + response.skip_ledger.included_records
        == response.skip_ledger.screen_pass
    )


def test_accumulation_audit_groups_outcomes_by_broker_quality():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    candles = _alternating_candles("BBCA", base, 25)
    candles.extend(_candle("BBCA", base + timedelta(days=i), Decimal("104")) for i in range(25, 31))
    candles.extend(_alternating_candles("BBRI", base, 25))
    candles.extend(_candle("BBRI", base + timedelta(days=i), Decimal("99")) for i in range(25, 31))

    summaries = [_summary("BBCA", base + timedelta(days=i), Decimal("110")) for i in range(18, 24)]
    summaries.append(
        _summary_with_brokers(
            "BBCA",
            signal_date,
            Decimal("110"),
            top_buyers=(_tx("AK", "90000000", "10000000"),),
        )
    )
    summaries.extend(
        _summary("BBRI", base + timedelta(days=i), Decimal("101")) for i in range(18, 24)
    )
    summaries.append(
        _summary_with_brokers(
            "BBRI",
            signal_date,
            Decimal("101"),
            top_buyers=(
                _tx("YP", "90000000", "10000000", BrokerType.LOCAL),
                _tx("XC", "50000000", "5000000", BrokerType.LOCAL),
            ),
        )
    )

    use_case = AccumulationAuditUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=["BBCA", "BBRI"],
            start_date=signal_date,
            end_date=signal_date,
            window_days=7,
            min_net_buy_days=1,
            min_accum_score=0,
            horizon_days=5,
        )
    )

    by_ticker = {record.ticker: record for record in response.records}
    assert by_ticker["BBCA"].broker_quality == "smart+"
    assert by_ticker["BBRI"].broker_quality == "noise+"

    broker_quality_stats = {
        stat.bucket: stat for stat in response.group_stats if stat.dimension == "broker_quality"
    }
    assert broker_quality_stats["smart+"].count == 1
    assert broker_quality_stats["noise+"].count == 1


def test_accumulation_audit_exit_simulation_reports_target_and_max_hold_stats():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    candles = _alternating_candles("BBCA", base, 25)
    candles.extend(
        [
            _ohlc(
                "BBCA",
                base + timedelta(days=25),
                Decimal("101"),
                Decimal("106"),
                Decimal("99"),
                Decimal("104"),
            ),
            _ohlc(
                "BBCA",
                base + timedelta(days=26),
                Decimal("104"),
                Decimal("105"),
                Decimal("102"),
                Decimal("103"),
            ),
            _ohlc(
                "BBCA",
                base + timedelta(days=27),
                Decimal("103"),
                Decimal("104"),
                Decimal("101"),
                Decimal("102"),
            ),
        ]
    )
    summaries = [_summary("BBCA", base + timedelta(days=i), Decimal("110")) for i in range(18, 25)]

    use_case = AccumulationAuditUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=["BBCA"],
            start_date=signal_date,
            end_date=signal_date,
            window_days=7,
            min_net_buy_days=1,
            min_accum_score=0,
            horizon_days=5,
            simulate_exits=True,
            take_profit_pcts=(5, 20),
            stop_loss_pcts=(3, 20),
            max_hold_days=(3,),
        )
    )

    target_stat = next(
        stat
        for stat in response.exit_simulations
        if stat.take_profit_pct == 5 and stat.stop_loss_pct == 3
    )
    assert target_stat.count == 1
    assert target_stat.avg_return_pct == 5.0
    assert target_stat.win_rate_pct == 100.0
    assert target_stat.avg_holding_days == 1.0
    assert target_stat.target_rate_pct == 100.0

    max_hold_stat = next(
        stat
        for stat in response.exit_simulations
        if stat.take_profit_pct == 20 and stat.stop_loss_pct == 20
    )
    assert max_hold_stat.avg_return_pct == 2.0
    assert max_hold_stat.max_hold_rate_pct == 100.0


def test_accumulation_audit_exit_simulation_can_prioritize_target_on_same_day():
    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=24)
    candles = _alternating_candles("BBCA", base, 25)
    candles.append(
        _ohlc(
            "BBCA",
            base + timedelta(days=25),
            Decimal("100"),
            Decimal("106"),
            Decimal("94"),
            Decimal("100"),
        )
    )
    summaries = [_summary("BBCA", base + timedelta(days=i), Decimal("110")) for i in range(18, 25)]

    use_case = AccumulationAuditUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=["BBCA"],
            start_date=signal_date,
            end_date=signal_date,
            window_days=7,
            min_net_buy_days=1,
            min_accum_score=0,
            horizon_days=5,
            simulate_exits=True,
            take_profit_pcts=(5,),
            stop_loss_pcts=(5,),
            max_hold_days=(1,),
            policy=AccumulationAuditPolicy(same_day_exit_priority="target_first"),
        )
    )

    stat = response.exit_simulations[0]
    assert stat.target_rate_pct == 100.0
    assert stat.avg_return_pct == 5.0


def test_accumulation_audit_uses_injected_screen_and_preserves_signal_score():
    """D8-1: audit records carry the same screen assessment score (shared path)."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from src.application.dto.assess_signal import AssessSignalResponse
    from src.application.dto.signal_evidence_execution_context import (
        SignalEvidenceExecutionContext,
    )
    from src.domain.value_objects.signal_assessment import (
        ACCUMULATION_DISCOVERY_IDENTITY,
        EntryQuality,
        SignalAssessment,
        SignalStrength,
    )

    base = date(2026, 1, 1)
    signal_date = base + timedelta(days=20)
    candles = [_candle("BBCA", base + timedelta(days=i), Decimal(100 + i)) for i in range(35)]
    summaries = [
        _summary("BBCA", base + timedelta(days=i), Decimal(100 + i)) for i in range(10, 21)
    ]

    assessment = AssessSignalResponse(
        ticker="BBCA",
        assessment=SignalAssessment(
            identity=ACCUMULATION_DISCOVERY_IDENTITY,
            ticker="BBCA",
            score=77,
            strength=SignalStrength.MODERATE,
            entry_quality=EntryQuality.WATCH,
            breakdown=(),
            rationale=("fixture",),
            snapshot_date=signal_date,
            signal_authority_coverage=0.55,
        ),
        signal_authority_coverage=0.55,
    )
    candidate = MagicMock()
    candidate.ticker = "BBCA"
    candidate.accum_score = 60.0
    candidate.consecutive_streak = 3
    candidate.net_buy_ratio = 0.5
    candidate.total_net_value = Decimal("1000000")
    candidate.avg_flow_ratio = 10.0
    candidate.vwap_discount_pct = 2.0
    candidate.rsi = 45.0
    candidate.bb_width_pctile = 0.3
    candidate.trend = "SIDE"
    candidate.current_price = Decimal("120")
    candidate.signal_assessment = assessment

    observation = SimpleNamespace(
        candidate=candidate,
        screen_result="pass",
    )
    screen_response = SimpleNamespace(
        candidates=[candidate],
        observation_candidates=[observation],
        total_tickers_checked=1,
        tickers_skipped=0,
    )
    fake_screen = MagicMock()
    fake_screen.execute.return_value = screen_response

    use_case = AccumulationAuditUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
        screen_use_case=fake_screen,
    )
    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=["BBCA"],
            start_date=signal_date,
            end_date=signal_date,
            window_days=7,
            min_net_buy_days=1,
            min_accum_score=0,
            horizon_days=5,
        )
    )

    assert fake_screen.execute.call_count == 1
    call_kwargs = fake_screen.execute.call_args
    assert call_kwargs.kwargs["execution_context"] is not None
    assert isinstance(call_kwargs.kwargs["execution_context"], SignalEvidenceExecutionContext)
    assert response.total_records == 1
    assert response.records[0].signal_score == 77
    assert response.records[0].signal_authority_coverage == 0.55
    assert response.skip_ledger.screen_pass == 1
    assert response.skip_ledger.included_records == 1
    assert response.claim_stamp.evaluation_role == "DESCRIPTIVE"
    assert any("DESCRIPTIVE" in w for w in response.warnings)
