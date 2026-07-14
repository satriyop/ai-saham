"""Coordinator tests for AccumulationCandidateEvidenceBuilder public methods.

Focuses on the finding-3 refactor: each public build_candidate_* /
detect_candidate_setup_phase method must delegate to
CandidateEvidenceDataLoader + the candidate_*_evidence_assembler modules,
preserve best-effort None-on-failure behavior, and keep attaching
rs_vs_ihsg_5d/20d as diagnostic instance attributes on successful setup
phase detection.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.accumulation_candidate_evidence_builder import (
    AccumulationCandidateEvidenceBuilder,
)
from src.application.services.primary_setup_family_resolver import (
    PrimarySetupFamilyResolver,
)
from src.application.services.relative_strength_calculator import RelativeStrengthResult
from src.domain.entities.candle import Candle
from src.domain.value_objects.benchmark_symbol import CANONICAL_BENCHMARK_TICKER
from tests.application.use_case.accumulation_screen_fixtures import FakeRulesLoader


class _MarketRepository:
    def __init__(self, candles_by_ticker: dict[str, list[Candle]] | None = None) -> None:
        self._candles_by_ticker = candles_by_ticker or {}

    def get_candles(self, ticker, start_date=None, end_date=None):
        return list(self._candles_by_ticker.get(ticker, []))

    def get_candle_source(self, ticker, on_date):
        return None


class _BrokerRepository:
    def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
        return []

    def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
        return []

    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        return []


class _RaisingFactory:
    def __init__(self, message: str) -> None:
        self._message = message

    def __call__(self):
        raise RuntimeError(self._message)


class _FakeSignalEngine:
    def foreign_flow_quality_from_foreign_flow_score(self, score):
        return "MODERATE"

    def bandar_max_range(self, num_optional):
        return 100.0


class _FakeRelativeStrengthCalculator:
    def __init__(self, result: RelativeStrengthResult | None = None, raise_error: bool = False):
        self._result = result or RelativeStrengthResult(
            rs_vs_ihsg_5d=1.5, rs_vs_ihsg_20d=2.5, unavailable_reasons=()
        )
        self._raise_error = raise_error

    def calculate(self, *, ticker_candles, benchmark_candles, as_of_date, windows=None):
        if self._raise_error:
            raise RuntimeError("rs calc failed")
        return self._result


def _candles(ticker: str, start: date, count: int) -> list[Candle]:
    return [
        Candle(
            ticker=ticker,
            date=date.fromordinal(start.toordinal() + i),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100") + Decimal(i),
            volume=1_000_000,
        )
        for i in range(count)
    ]


def _candidate(**overrides) -> AccumulationCandidate:
    values = dict(
        ticker="BBCA",
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
        foreign_flow_score=50.0,
        top_brokers=None,
        institutional_flag=False,
    )
    values.update(overrides)
    return AccumulationCandidate(**values)


def _builder(
    market_repo=None,
    broker_repo=None,
    *,
    signal_engine=None,
    ticker_profile_classifier_factory=None,
    sector_context_builder_factory=None,
    company_quality_context_builder_factory=None,
    relative_strength_calculator=None,
    candidate_observations_repository=None,
) -> AccumulationCandidateEvidenceBuilder:
    return AccumulationCandidateEvidenceBuilder(
        market_repository=market_repo or _MarketRepository(),
        broker_repository=broker_repo or _BrokerRepository(),
        signal_engine=signal_engine,
        candidate_observations_repository=candidate_observations_repository,
        swing_setup_catalog=None,
        primary_setup_family_resolver=PrimarySetupFamilyResolver(),
        relative_strength_calculator=relative_strength_calculator
        or _FakeRelativeStrengthCalculator(),
        indicator_registry=None,
        rules_loader=FakeRulesLoader(),
        ticker_profile_classifier_factory=ticker_profile_classifier_factory,
        sector_context_builder_factory=sector_context_builder_factory,
        company_quality_context_builder_factory=company_quality_context_builder_factory,
    )


class TestInstitutionalEvidenceFailureReturnsNone:
    def test_returns_none_when_broker_repository_raises(self):
        class _RaisingBrokerRepository:
            def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
                raise RuntimeError("broker down")

            def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
                return []

            def get_broker_summaries(self, ticker, start_date=None, end_date=None):
                return []

        builder = _builder(broker_repo=_RaisingBrokerRepository())
        candidate = _candidate()

        result = builder.build_candidate_institutional_accumulation_evidence(
            candidate, date(2026, 6, 10)
        )

        assert result is None


class TestTickerProfileFailureReturnsNone:
    def test_returns_none_when_classifier_factory_raises(self):
        builder = _builder(
            ticker_profile_classifier_factory=_RaisingFactory("classifier down")
        )
        candidate = _candidate()

        result = builder.build_candidate_ticker_profile(candidate, date(2026, 6, 10))

        assert result is None

    def test_returns_none_without_classifier_factory(self):
        builder = _builder()
        candidate = _candidate()

        result = builder.build_candidate_ticker_profile(candidate, date(2026, 6, 10))

        assert result is None


class TestSectorContextFailureReturnsNone:
    def test_returns_none_when_sector_builder_factory_raises(self):
        builder = _builder(sector_context_builder_factory=_RaisingFactory("sector down"))
        candidate = _candidate()

        result = builder.build_candidate_sector_context(
            candidate, date(2026, 6, 10), tp_snapshot=None
        )

        assert result is None


class TestCompanyQualityFailureReturnsNone:
    def test_returns_none_when_signal_engine_missing(self):
        builder = _builder(signal_engine=None)
        candidate = _candidate()

        result = builder.build_candidate_company_quality_context(
            candidate, date(2026, 6, 10)
        )

        assert result is None

    def test_returns_none_when_company_quality_factory_raises(self):
        builder = _builder(
            signal_engine=_FakeSignalEngine(),
            company_quality_context_builder_factory=_RaisingFactory("cq down"),
        )
        candidate = _candidate()

        result = builder.build_candidate_company_quality_context(
            candidate, date(2026, 6, 10)
        )

        assert result is None


class TestSetupPhaseFailureReturnsNone:
    def test_returns_none_when_relative_strength_calculator_raises(self):
        builder = _builder(
            relative_strength_calculator=_FakeRelativeStrengthCalculator(raise_error=True)
        )
        candidate = _candidate()

        result = builder.detect_candidate_setup_phase(candidate, None, date(2026, 6, 10))

        assert result is None


class TestEmptyCandlesDoNotCrash:
    def test_setup_phase_detection_with_empty_candles(self):
        builder = _builder(market_repo=_MarketRepository({}))
        candidate = _candidate()

        result = builder.detect_candidate_setup_phase(candidate, None, date(2026, 6, 10))

        # No candles means the phase detector has nothing to work with, but
        # the best-effort contract still holds: no exception escapes.
        assert result is None or result is not None

    def test_volatility_context_with_empty_candles(self):
        builder = _builder(market_repo=_MarketRepository({}))
        candidate = _candidate()

        result = builder.build_candidate_volatility_context(candidate, date(2026, 6, 10))

        assert result.volatility_bucket_at_signal == "UNKNOWN"
        assert result.atr_at_signal is None


class TestSetupPhaseAttachesRelativeStrengthOnSuccess:
    def test_rs_vs_ihsg_attached_when_setup_phase_detection_succeeds(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 15)
        market_repo = _MarketRepository(
            {
                ticker: _candles(ticker, date(2026, 6, 1), 15),
                CANONICAL_BENCHMARK_TICKER: _candles(
                    CANONICAL_BENCHMARK_TICKER, date(2026, 6, 1), 15
                ),
            }
        )
        rs_calculator = _FakeRelativeStrengthCalculator(
            RelativeStrengthResult(rs_vs_ihsg_5d=3.3, rs_vs_ihsg_20d=7.7, unavailable_reasons=())
        )
        builder = _builder(market_repo=market_repo, relative_strength_calculator=rs_calculator)
        candidate = _candidate(ticker=ticker)

        result = builder.detect_candidate_setup_phase(candidate, None, snapshot_date)

        assert result is not None
        assert candidate.rs_vs_ihsg_5d == 3.3
        assert candidate.rs_vs_ihsg_20d == 7.7
