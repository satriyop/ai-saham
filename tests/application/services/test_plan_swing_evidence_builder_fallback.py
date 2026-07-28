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

from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextEvidenceBuilder,
)
from src.application.services.institutional_accumulation_evidence_builder import (
    InstitutionalAccumulationEvidenceBuilder,
)
from src.application.services.plan_swing_evidence_builder import (
    PlanSwingEvidenceBuilder,
)
from src.application.services.sector_context_evidence_builder import (
    SectorContextEvidenceBuilder,
)
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader


def _builder(**factory_overrides) -> PlanSwingEvidenceBuilder:
    return PlanSwingEvidenceBuilder(
        market_repository=None,
        broker_repository=None,
        registry=None,
        rules_loader=RulesYamlLoader(),
        flow_confirmation_builder=None,
        candidate_observations_repository=None,
        signal_engine=None,
        corporate_action_risk_use_case=None,
        **factory_overrides,
    )


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


class TestFallbackWithoutInjectedFactories:
    def test_institutional_accumulation_builder_falls_back_to_pure_default(self):
        builder = _builder()
        ia_builder = builder._institutional_assembler._builder_factory()

        assert isinstance(ia_builder, InstitutionalAccumulationEvidenceBuilder)

    def test_sector_context_builder_falls_back_to_pure_default(self):
        builder = _builder()
        sc_builder = builder._sector_context_builder_factory()

        assert isinstance(sc_builder, SectorContextEvidenceBuilder)
        # Empty sector index is an acceptable fallback per spec.
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


class TestPublicBuildFlowWithoutInjectedFactories:
    """build() end-to-end: no factories injected, but minimum input data exists."""

    def test_build_attempts_fallback_evidence_when_no_factories_injected(self):
        ticker = "BBCA"
        snapshot_date = date(2026, 6, 10)
        candles = _candles(ticker)

        from src.application.services.flow_confirmation_evidence_builder import (
            FlowConfirmationEvidenceBuilder,
        )

        builder = PlanSwingEvidenceBuilder(
            market_repository=_StubMarketRepository(candles),
            broker_repository=_StubBrokerRepository(),
            registry=None,
            rules_loader=RulesYamlLoader(),
            flow_confirmation_builder=FlowConfirmationEvidenceBuilder(),
            candidate_observations_repository=None,
            signal_engine=None,
            corporate_action_risk_use_case=None,
            # No institutional/sector/company-quality factories injected.
        )

        result = builder.build(
            ticker=ticker,
            snapshot_date=snapshot_date,
            benchmark="IHSG",
            candles=candles,
            accumulation_evaluation=None,
            setup_eval=None,
            setup_name=None,
            strategy_name=None,
            swing_policy=None,
        )

        # Institutional accumulation evidence is attempted/built via the pure
        # default builder, not skipped just because no factory was injected.
        assert result.institutional_accumulation_evidence is not None
        assert result.institutional_accumulation_evidence.ticker == ticker
        assert result.institutional_accumulation_evidence.snapshot_date == snapshot_date

        # Sector context evidence is attempted/built via the pure default
        # builder (empty sector index fallback), not skipped.
        assert result.sector_context_evidence is not None
        assert result.sector_context_evidence.sector_regime == "UNKNOWN"
