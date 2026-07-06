"""Tests for SectorContextEvidence value object (Phase H)."""

import pytest

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.sector_context_evidence import SectorContextEvidence


def _make(**overrides) -> SectorContextEvidence:
    defaults = dict(
        sector="Finance",
        peer_count=5,
        peer_tickers=("BBRI", "BBNI", "BMRI", "BDMN", "BNGA"),
        sector_20d_return=0.025,
        sector_vs_ihsg_20d=0.012,
        sector_breadth=0.80,
        ticker_vs_sector_rs=0.008,
        sector_regime="BULLISH",
        coverage_score=1.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("sector_20d_return computed from 5 peers",),
        unavailable_reasons=(),
    )
    defaults.update(overrides)
    return SectorContextEvidence(**defaults)


class TestSectorContextEvidenceValidation:
    def test_valid_bullish_construction(self):
        ev = _make()
        assert ev.sector_regime == "BULLISH"
        assert ev.coverage_score == 1.0
        assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC

    def test_invalid_coverage_score_high(self):
        with pytest.raises(ValueError, match="coverage_score"):
            _make(coverage_score=1.1)

    def test_invalid_coverage_score_negative(self):
        with pytest.raises(ValueError, match="coverage_score"):
            _make(coverage_score=-0.01)

    def test_invalid_sector_regime(self):
        with pytest.raises(ValueError, match="sector_regime"):
            _make(sector_regime="SIDEWAYS")

    def test_invalid_sector_breadth_high(self):
        with pytest.raises(ValueError, match="sector_breadth"):
            _make(sector_breadth=1.1)

    def test_invalid_sector_breadth_negative(self):
        with pytest.raises(ValueError, match="sector_breadth"):
            _make(sector_breadth=-0.01)

    def test_invalid_sector_20d_return_too_high(self):
        with pytest.raises(ValueError, match="sector_20d_return"):
            _make(sector_20d_return=6.0)

    def test_none_optionals_valid(self):
        ev = _make(
            sector=None,
            sector_20d_return=None,
            sector_vs_ihsg_20d=None,
            sector_breadth=None,
            ticker_vs_sector_rs=None,
            sector_regime="UNKNOWN",
            coverage_score=0.0,
        )
        assert ev.sector_regime == "UNKNOWN"
        assert ev.sector_20d_return is None


class TestSectorContextEvidenceSerialization:
    def test_round_trip_full(self):
        ev = _make()
        d = ev.to_dict()
        ev2 = SectorContextEvidence.from_dict(d)
        assert ev2.sector == ev.sector
        assert ev2.peer_count == ev.peer_count
        assert ev2.sector_20d_return == pytest.approx(ev.sector_20d_return, abs=1e-6)
        assert ev2.sector_vs_ihsg_20d == pytest.approx(ev.sector_vs_ihsg_20d, abs=1e-6)
        assert ev2.sector_breadth == pytest.approx(ev.sector_breadth, abs=1e-4)
        assert ev2.ticker_vs_sector_rs == pytest.approx(ev.ticker_vs_sector_rs, abs=1e-6)
        assert ev2.sector_regime == ev.sector_regime
        assert ev2.coverage_score == pytest.approx(ev.coverage_score, abs=1e-4)
        assert ev2.evidence_status == ev.evidence_status
        assert ev2.peer_tickers == ev.peer_tickers

    def test_round_trip_none_optionals(self):
        ev = _make(
            sector=None,
            sector_20d_return=None,
            sector_vs_ihsg_20d=None,
            sector_breadth=None,
            ticker_vs_sector_rs=None,
            sector_regime="UNKNOWN",
            coverage_score=0.0,
            peer_count=0,
            peer_tickers=(),
        )
        d = ev.to_dict()
        ev2 = SectorContextEvidence.from_dict(d)
        assert ev2.sector is None
        assert ev2.sector_20d_return is None
        assert ev2.sector_regime == "UNKNOWN"

    def test_from_dict_missing_keys_uses_defaults(self):
        ev = SectorContextEvidence.from_dict({})
        assert ev.sector is None
        assert ev.peer_count == 0
        assert ev.sector_regime == "UNKNOWN"
        assert ev.coverage_score == 0.0
        assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC

    def test_to_dict_has_all_fields(self):
        ev = _make()
        d = ev.to_dict()
        assert "sector" in d
        assert "peer_count" in d
        assert "peer_tickers" in d
        assert "sector_20d_return" in d
        assert "sector_vs_ihsg_20d" in d
        assert "sector_breadth" in d
        assert "ticker_vs_sector_rs" in d
        assert "sector_regime" in d
        assert "coverage_score" in d
        assert "evidence_status" in d
        assert "reasons" in d
        assert "unavailable_reasons" in d
        assert d["evidence_status"] == "DIAGNOSTIC"


class TestSectorContextEvidenceUnavailable:
    def test_unavailable_factory(self):
        ev = SectorContextEvidence.unavailable(reason="no_sector_peers")
        assert ev.peer_count == 0
        assert ev.sector_regime == "UNKNOWN"
        assert ev.coverage_score == 0.0
        assert "no_sector_peers" in ev.unavailable_reasons
        assert ev.sector_20d_return is None

    def test_regime_variants(self):
        for regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNKNOWN"):
            ev = _make(sector_regime=regime)
            assert ev.sector_regime == regime
