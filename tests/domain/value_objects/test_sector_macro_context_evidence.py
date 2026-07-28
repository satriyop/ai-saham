"""Tests for SectorMacroContextEvidence value object (ADR-053)."""

from datetime import date

import pytest

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.sector_macro_context_evidence import (
    MacroFactorScore,
    SectorMacroContextEvidence,
)


def _factor(**overrides) -> MacroFactorScore:
    defaults = dict(
        name="coal_futures",
        series="MTF=F",
        value=0.06,
        score=1.0,
        weight=0.65,
        label="FAVORABLE",
        rationale="coal up",
    )
    defaults.update(overrides)
    return MacroFactorScore(**defaults)


def _make(**overrides) -> SectorMacroContextEvidence:
    defaults = dict(
        sector_group="energy",
        as_of_date=date(2026, 7, 1),
        factors=(_factor(),),
        composite_score=0.85,
        macro_regime="SUPPORTIVE",
        coverage_score=1.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("macro_regime:SUPPORTIVE",),
        unavailable_reasons=(),
    )
    defaults.update(overrides)
    return SectorMacroContextEvidence(**defaults)


class TestMacroFactorScore:
    def test_invalid_label(self):
        with pytest.raises(ValueError, match="label"):
            _factor(label="BULLISH")

    def test_invalid_score(self):
        with pytest.raises(ValueError, match="score"):
            _factor(score=1.1)

    def test_negative_weight(self):
        with pytest.raises(ValueError, match="weight"):
            _factor(weight=-0.1)


class TestSectorMacroContextEvidenceValidation:
    def test_valid_supportive(self):
        ev = _make()
        assert ev.macro_regime == "SUPPORTIVE"
        assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC

    def test_invalid_coverage(self):
        with pytest.raises(ValueError, match="coverage_score"):
            _make(coverage_score=1.5)

    def test_invalid_macro_regime(self):
        with pytest.raises(ValueError, match="macro_regime"):
            _make(macro_regime="BULLISH")

    def test_invalid_composite(self):
        with pytest.raises(ValueError, match="composite_score"):
            _make(composite_score=1.2)

    def test_regime_variants(self):
        for regime in ("SUPPORTIVE", "NEUTRAL", "HEADWIND", "UNKNOWN"):
            assert _make(macro_regime=regime).macro_regime == regime


class TestSerialization:
    def test_round_trip(self):
        ev = _make()
        ev2 = SectorMacroContextEvidence.from_dict(ev.to_dict())
        assert ev2.sector_group == ev.sector_group
        assert ev2.as_of_date == ev.as_of_date
        assert ev2.macro_regime == ev.macro_regime
        assert ev2.composite_score == pytest.approx(ev.composite_score)
        assert len(ev2.factors) == 1
        assert ev2.factors[0].name == "coal_futures"
        assert ev2.factors[0].score == pytest.approx(1.0)

    def test_from_dict_defaults(self):
        ev = SectorMacroContextEvidence.from_dict({})
        assert ev.macro_regime == "UNKNOWN"
        assert ev.coverage_score == 0.0
        assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC
        assert ev.factors == ()

    def test_to_dict_keys(self):
        d = _make().to_dict()
        for key in (
            "sector_group",
            "as_of_date",
            "factors",
            "composite_score",
            "macro_regime",
            "coverage_score",
            "evidence_status",
            "reasons",
            "unavailable_reasons",
            "metadata",
        ):
            assert key in d


class TestUnavailable:
    def test_factory(self):
        ev = SectorMacroContextEvidence.unavailable(
            reason="sector_map:missing:bank",
            sector_group="bank",
            as_of_date=date(2026, 7, 1),
        )
        assert ev.macro_regime == "UNKNOWN"
        assert ev.coverage_score == 0.0
        assert ev.composite_score is None
        assert "sector_map:missing:bank" in ev.unavailable_reasons
        assert ev.sector_group == "bank"
