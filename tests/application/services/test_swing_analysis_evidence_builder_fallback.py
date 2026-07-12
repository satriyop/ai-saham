"""Regression tests: missing optional evidence factories must not suppress evidence.

Guards the finding-19 YAML-boundary refactor from silently disabling
institutional accumulation / sector context / company quality context
evidence when the CLI composition root does not inject a factory. Without
an injected factory, the builder must still construct a pure-default
application builder (no YAML/file I/O) rather than skip the evidence.
"""

from __future__ import annotations

from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextEvidenceBuilder,
)
from src.application.services.institutional_accumulation_evidence_builder import (
    InstitutionalAccumulationEvidenceBuilder,
)
from src.application.services.sector_context_evidence_builder import (
    SectorContextEvidenceBuilder,
)
from src.application.services.swing_analysis_evidence_builder import (
    SwingAnalysisEvidenceBuilder,
)


def _builder(**factory_overrides) -> SwingAnalysisEvidenceBuilder:
    return SwingAnalysisEvidenceBuilder(
        market_repository=None,
        broker_repository=None,
        registry=None,
        flow_confirmation_builder=None,
        candidate_observations_repository=None,
        signal_engine=None,
        corporate_action_risk_use_case=None,
        **factory_overrides,
    )


class TestFallbackWithoutInjectedFactories:
    def test_institutional_accumulation_builder_falls_back_to_pure_default(self):
        builder = _builder()
        ia_builder = builder._institutional_accumulation_builder()

        assert isinstance(ia_builder, InstitutionalAccumulationEvidenceBuilder)

    def test_sector_context_builder_falls_back_to_pure_default(self):
        builder = _builder()
        sc_builder = builder._sector_context_builder()

        assert isinstance(sc_builder, SectorContextEvidenceBuilder)
        # Empty sector index is an acceptable fallback per spec.
        assert sc_builder.peers_for_ticker("BBCA") == ()

    def test_company_quality_context_builder_falls_back_to_pure_default(self):
        builder = _builder()
        cq_builder = builder._company_quality_context_builder()

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
        ia_builder = builder._institutional_accumulation_builder()

        assert captured.get("called") is True
        assert ia_builder._config is sentinel_config

    def test_sector_context_builder_uses_injected_factory(self):
        sentinel = object()
        builder = _builder(sector_context_builder_factory=lambda: sentinel)

        assert builder._sector_context_builder() is sentinel

    def test_company_quality_context_builder_uses_injected_factory(self):
        sentinel = object()
        builder = _builder(company_quality_context_builder_factory=lambda: sentinel)

        assert builder._company_quality_context_builder() is sentinel
