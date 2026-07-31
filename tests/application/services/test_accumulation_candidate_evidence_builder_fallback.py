"""Regression tests: missing optional evidence factories must not suppress evidence.

Guards the finding-19 YAML-boundary refactor from silently disabling
institutional accumulation / sector context / company quality context
evidence when the CLI composition root does not inject a factory. Without
an injected factory, the builder must still construct a pure-default
application builder (no YAML/file I/O) rather than skip the evidence.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.accumulation_candidate_evidence_builder import (
    AccumulationCandidateEvidenceBuilder,
)
from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextEvidenceBuilder,
)
from src.application.services.institutional_accumulation_evidence_builder import (
    InstitutionalAccumulationEvidenceBuilder,
)
from src.application.services.sector_context_evidence_builder import (
    SectorContextEvidenceBuilder,
)
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from tests.application.use_case.accumulation_screen_fixtures import FakeRulesLoader


def _builder(**factory_overrides) -> AccumulationCandidateEvidenceBuilder:
    return AccumulationCandidateEvidenceBuilder(
        market_repository=None,
        broker_repository=None,
        signal_engine=None,
        candidate_observations_repository=None,
        swing_setup_catalog=None,
        primary_setup_family_resolver=None,
        benchmark_excess_return_calculator=None,
        indicator_registry=None,
        rules_loader=FakeRulesLoader(),
        **factory_overrides,
    )


class TestFallbackWithoutInjectedFactories:
    def test_institutional_accumulation_builder_falls_back_to_pure_default(self):
        builder = _builder()
        ia_builder = builder._institutional_assembler._builder_factory()

        assert isinstance(ia_builder, InstitutionalAccumulationEvidenceBuilder)

    def test_sector_context_builder_falls_back_to_pure_default(self):
        builder = _builder()
        sc_builder = builder._sector_context_builder_factory()

        assert isinstance(sc_builder, SectorContextEvidenceBuilder)
        assert sc_builder.peers_for_ticker("BBCA") == ()

    def test_company_quality_context_builder_falls_back_to_pure_default(self):
        builder = _builder()
        cq_builder = builder._company_quality_assembler._builder_factory()

        assert isinstance(cq_builder, CompanyQualityContextEvidenceBuilder)


class _FakeInstitutionalAccumulationConfig:
    """Minimal stand-in satisfying InstitutionalAccumulationEvidenceBuilder.__init__."""

    foreign_broker_codes: frozenset[str] = frozenset()

    def validate(self) -> None:
        pass


class TestInjectedFactoriesArePreferred:
    def test_institutional_accumulation_builder_uses_injected_factory(self):
        sentinel_config = _FakeInstitutionalAccumulationConfig()
        captured = {}

        def factory():
            captured["called"] = True
            return sentinel_config

        builder = _builder(institutional_accumulation_config_factory=factory)
        ia_builder = builder._institutional_assembler._builder_factory()

        assert captured.get("called") is True
        assert ia_builder._config is sentinel_config

    def test_sector_context_builder_uses_injected_factory(self):
        sentinel = object()
        builder = _builder(sector_context_builder_factory=lambda: sentinel)

        assert builder._sector_context_builder_factory() is sentinel

    def test_company_quality_context_builder_uses_injected_factory(self):
        sentinel = object()
        builder = _builder(company_quality_context_builder_factory=lambda: sentinel)

        assert builder._company_quality_assembler._builder_factory() is sentinel


class TestCompanyQualityContextStillRequiresSignalEngine:
    def test_build_candidate_company_quality_context_returns_none_without_signal_engine(self):
        builder = _builder()
        result = builder.build_candidate_company_quality_context(
            candidate=object(),
            snapshot_date=date(2026, 7, 3),
        )

        assert result is None


class _StubMarketRepository(MarketDataRepository):
    """Minimal MarketDataRepository returning a fixed candle series."""

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
        return False

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        rows = self.get_candles(ticker)
        if not rows:
            return None
        return rows[0].date, rows[-1].date

    def list_tickers_with_candles_between(self, start_date, end_date):
        return []


class _StubBrokerRepository(BrokerDataRepository):
    """Minimal BrokerDataRepository with no broker/flow data (empty results)."""

    def save_broker_summary(self, summary) -> None:
        pass

    def save_broker_summaries(self, summaries) -> None:
        pass

    def get_broker_summary(self, ticker: str, target_date: date):
        return None

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list:
        return []

    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        source: str | None = None,
    ) -> bool:
        return False

    def get_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        return None


def _candles(ticker: str, count: int = 10) -> list[Candle]:
    base = date(2026, 6, 1)
    return [
        Candle(
            ticker=ticker,
            date=date.fromordinal(base.toordinal() + i),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1_000_000,
        )
        for i in range(count)
    ]


def _candidate(ticker: str = "BBCA") -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker=ticker,
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
        accum_score=50.0,
        top_brokers=None,
        institutional_flag=False,
    )


def _full_builder(**factory_overrides) -> AccumulationCandidateEvidenceBuilder:
    ticker = "BBCA"
    return AccumulationCandidateEvidenceBuilder(
        market_repository=_StubMarketRepository(_candles(ticker)),
        broker_repository=_StubBrokerRepository(),
        signal_engine=None,
        candidate_observations_repository=None,
        swing_setup_catalog=None,
        primary_setup_family_resolver=None,
        benchmark_excess_return_calculator=None,
        indicator_registry=None,
        rules_loader=FakeRulesLoader(),
        **factory_overrides,
    )


class TestPublicBuildFlowWithoutInjectedFactories:
    """Public build_candidate_* methods: no factories injected, minimum input data exists."""

    def test_build_candidate_institutional_accumulation_evidence_not_none(self):
        builder = _full_builder()
        candidate = _candidate()
        snapshot_date = date(2026, 6, 10)

        result = builder.build_candidate_institutional_accumulation_evidence(
            candidate, snapshot_date
        )

        assert result is not None
        assert result.ticker == candidate.ticker
        assert result.snapshot_date == snapshot_date

    def test_build_candidate_sector_context_not_none_with_empty_peer_index_fallback(self):
        builder = _full_builder()
        candidate = _candidate()
        snapshot_date = date(2026, 6, 10)

        result = builder.build_candidate_sector_context(candidate, snapshot_date, tp_snapshot=None)

        assert result is not None
        # No injected sector factory: falls back to an empty sector index,
        # so no peers are found and the regime is UNKNOWN — not skipped.
        assert result.sector_regime == "UNKNOWN"
