"""Shared fixtures and mocks for accumulation screen tests."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.ports.rules_loader import RulesLoader
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.company_fundamentals import CompanyFundamentals
from src.infrastructure.config.ticker_profile_config_loader import (
    create_ticker_profile_classifier,
)


class FakeRulesLoader(RulesLoader):
    """Minimal RulesLoader stand-in for tests that require the constructor
    parameter but never exercise real YAML parsing (no strategy_name set,
    or strategy_name resolution fails before load() is reached).
    """

    def load(self, path=None, registry=None):
        raise NotImplementedError(
            "FakeRulesLoader does not parse rules — inject a real loader "
            "if this test needs strategy evidence to actually resolve"
        )

    def load_from_string(self, content, registry=None, source_name="<generated>"):
        raise NotImplementedError(
            "FakeRulesLoader does not parse rules — inject a real loader "
            "if this test needs strategy evidence to actually resolve"
        )


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


class FakeATRRegistry:
    """Mirrors FakeRegistry from test_plan_swing_workflow.py: returns a
    fixed ATR(14) value so volatility-context fingerprint tests are
    deterministic regardless of the real indicator registry's plugin
    discovery/computation."""

    def compute(self, name: str, candles, period: int):
        if name == "ATR" and candles:
            return [(candles[-1].date, Decimal("5"))]
        return []


class EmptyATRRegistry:
    """Simulates insufficient candle history: ATR compute returns no values."""

    def compute(self, name: str, candles, period: int):
        return []


class RaisingATRRegistry:
    """Simulates a registry that raises during ATR computation."""

    def compute(self, name: str, candles, period: int):
        raise RuntimeError("ATR plugin unavailable")


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


def _summary_net(
    ticker: str,
    day: date,
    *,
    foreign_buy_value: Decimal,
    foreign_sell_value: Decimal,
) -> BrokerSummary:
    """BrokerSummary with explicit foreign buy/sell IDR for absorption tests."""
    return BrokerSummary(
        ticker=ticker,
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=foreign_buy_value,
        foreign_sell_value=foreign_sell_value,
        foreign_buy_lot=10_000,
        foreign_sell_lot=10_000,
        total_value=foreign_buy_value + foreign_sell_value,
        total_lot=20_000,
    )


def _weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _daily_flow(
    ticker: str,
    day: date,
    broker_code: str,
    net_lot: int,
    *,
    net_value: Decimal | None = None,
) -> BrokerDailyFlow:
    resolved_net_value = net_value if net_value is not None else Decimal(net_lot * 100 * 1000)
    buy_value = resolved_net_value if resolved_net_value > 0 else Decimal("0")
    sell_value = -resolved_net_value if resolved_net_value < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker=ticker,
        broker_code=broker_code,
        broker_name=broker_code,
        date=day,
        buy_lot=max(net_lot, 0),
        sell_lot=max(-net_lot, 0),
        net_lot=net_lot,
        buy_value=buy_value if net_value is not None else Decimal(max(net_lot, 0) * 100 * 1000),
        sell_value=sell_value if net_value is not None else Decimal(max(-net_lot, 0) * 100 * 1000),
        net_value=resolved_net_value,
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
            indicator_registry=IndicatorRegistry(),
            broker_repository=MockBrokerRepositoryWithDaily(summaries, daily_flows),
            market_repository=MockMarketRepository(candles),
            rules_loader=FakeRulesLoader(),
            signal_engine=SignalEngine(config=SignalEngineConfig()),
        ),
        session_dates,
    )


def _make_use_case_with_fundamentals(piotroski_score: int | None):
    """Build a use case with a fundamentals_provider stub returning the given F-Score."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

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
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        fundamentals_provider=fund_prov,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    return use_case, as_of


def _make_use_case_with_all_providers(
    market_cap_idr: int | None,
    piotroski_score: int | None,
    *,
    candidate_observations_repository=None,
):
    """Build a use case with all enrichment providers mocked so we can assert call counts."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

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
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        fundamentals_provider=fund_prov,
        seasonality_provider=seasonality_prov,
        bandar_detector_provider=bandar_prov,
        analyst_consensus_provider=analyst_prov,
        candidate_observations_repository=candidate_observations_repository,
        ticker_profile_classifier_factory=create_ticker_profile_classifier,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    return use_case, as_of, fund_prov, seasonality_prov, bandar_prov, analyst_prov


class SpyCandidateObservationsRepository:
    """Records immutable learning observation inserts for assertion."""

    def __init__(self):
        self.saved: list = []
        self.risk_saved: list = []
        self.raise_on_save: Exception | None = None

    def add_observation(self, observation):
        if self.raise_on_save is not None:
            raise self.raise_on_save
        self.saved.append(observation)
        return True

    def list_observations(self, purpose, *, compatibility_id=None):
        return []


def record_observations(use_case: AccumulationScreenUseCase, request):
    """Run the screen and persist via the explicit canonical recorder.

    AccumulationScreenUseCase.execute() is read-only (S1); tests that assert
    on a SpyCandidateObservationsRepository must go through the recorder
    instead of calling execute() directly. Returns the full
    RecordAccumulationObservationsResult (response + recorded_count).

    Production wiring goes through create_accumulation_screen_use_case_bundle()
    in accumulation_screen_factory.py, which builds an equivalently-configured
    AccumulationCandidateObservationPersister from the same constructor inputs
    (AccumulationScreenUseCase never builds or exposes the recorder itself).
    Here in tests we already hold the constructed use_case, so we reuse its
    own private collaborators directly to build the persister — a test-only
    shortcut, not a pattern for production code.
    """
    from src.application.services.accumulation_candidate_observation_persister import (
        AccumulationCandidateObservationPersister,
    )
    from src.application.use_case.record_accumulation_observations_use_case import (
        RecordAccumulationObservationsUseCase,
    )

    persister = AccumulationCandidateObservationPersister(
        candidate_observations_repository=use_case._candidate_observations_repo,
        candidate_evidence_builder=use_case._candidate_evidence_builder,
        setup_family_resolver=use_case._setup_family_resolver,
        swing_setup_catalog=use_case._swing_setup_catalog,
    )
    recorder = RecordAccumulationObservationsUseCase(
        screen_use_case=use_case,
        observation_persister=persister,
    )
    context = make_signal_evidence_execution_context(request.as_of_date or date.today())
    return recorder.execute(request, execution_context=context)


def execute_and_record(use_case: AccumulationScreenUseCase, request):
    """Like record_observations(), but returns only the screen response —
    for tests that don't need recorded_count."""
    return record_observations(use_case, request).response


def make_signal_evidence_execution_context(
    as_of: date,
    *,
    source_availability_use_case=None,
) -> SignalEvidenceExecutionContext:
    from datetime import datetime

    from src.application.dto.signal_evidence_execution_context import (
        SignalEvidenceExecutionContext,
    )
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )
    from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
    from src.domain.value_objects.signal_artifact_identity import (
        SemanticCompatibilityId,
    )
    from src.domain.value_objects.signal_semantic_contract import (
        ACCUMULATION_DISCOVERY_CONTRACT,
    )

    session = EffectiveMarketSession(
        run_at=datetime.combine(as_of, MARKET_CLOSE, tzinfo=IDX_TIMEZONE),
        decision_at=datetime.combine(as_of, MARKET_CLOSE, tzinfo=IDX_TIMEZONE),
        latest_completed_session=as_of,
        analysis_as_of=as_of,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
    )
    return SignalEvidenceExecutionContext(
        effective_session=session,
        source_availability_use_case=source_availability_use_case,
        # Lean DQ-003 identity so the canonical capture path (record → persist)
        # accepts the write. The persister rejects any other contract and
        # fail-closes on a None compatibility id.
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=SemanticCompatibilityId("sha256:" + "0" * 64),
    )
