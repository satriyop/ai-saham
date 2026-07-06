"""
Tests for SetupEvidenceBuilder (Phase 2 of SignalEngine refactor).

Deterministic fixtures only — no live providers. Uses SimpleNamespace stand-ins
for AccumulationCandidate and SetupEvaluation to avoid domain coupling.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from src.application.services.setup_evidence_builder import SetupEvidenceBuilder
from src.domain.value_objects.factor_evidence import Freshness


def _candidate(
    *,
    ticker: str = "BBCA",
    trend: str | None = "UP",
    rsi: float | None = 55.0,
    bb_width_pctile: float | None = 0.25,
    vwap_discount_pct: float | None = 1.5,
    vwap_pct: float | None = -0.5,
    latest_candle_date: date | None = date(2026, 1, 1),
) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        trend=trend,
        rsi=rsi,
        bb_width_pctile=bb_width_pctile,
        vwap_discount_pct=vwap_discount_pct,
        vwap_pct=vwap_pct,
        latest_candle_date=latest_candle_date,
    )


def _setup_eval(
    *,
    name: str = "pullback_uptrend",
    match: str = "MATCH",
    failed_reasons: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        match=SimpleNamespace(value=match),
        failed_reasons=failed_reasons,
    )


def test_match_translates_to_strength():
    builder = SetupEvidenceBuilder()
    assert builder.build(_candidate(), _setup_eval(match="MATCH")).match_strength == 100.0
    assert builder.build(_candidate(), _setup_eval(match="PARTIAL")).match_strength == 60.0
    assert builder.build(_candidate(), _setup_eval(match="NO_MATCH")).match_strength == 20.0


def test_failed_gates_threaded():
    reasons = ("rsi too high", "not near support")
    evidence = SetupEvidenceBuilder().build(
        _candidate(), _setup_eval(failed_reasons=reasons)
    )
    assert evidence.failed_gates == reasons


def test_rs_missing_when_date_before_ihsg_available():
    evidence = SetupEvidenceBuilder().build(
        _candidate(),
        _setup_eval(),
        rs_vs_ihsg_5d=0.5,
        analysis_date=date(2025, 6, 30),
    )
    assert evidence.rs_freshness is Freshness.MISSING
    assert evidence.rs_vs_ihsg_5d is None


def test_rs_fresh_when_date_after_ihsg_available():
    evidence = SetupEvidenceBuilder().build(
        _candidate(),
        _setup_eval(),
        rs_vs_ihsg_5d=0.5,
        analysis_date=date(2025, 7, 1),
    )
    assert evidence.rs_freshness is Freshness.FRESH
    assert evidence.rs_vs_ihsg_5d == 0.5


def test_rs_missing_when_no_value():
    evidence = SetupEvidenceBuilder().build(
        _candidate(),
        _setup_eval(),
        rs_vs_ihsg_5d=None,
        analysis_date=date(2026, 1, 1),
    )
    assert evidence.rs_freshness is Freshness.MISSING
    assert evidence.rs_vs_ihsg_5d is None


def test_volume_fresh_for_local_idx_stock_source():
    evidence = SetupEvidenceBuilder().build(
        _candidate(),
        _setup_eval(),
        volume_trend_ratio=1.2,
        candle_source="idx",
    )
    assert evidence.volume_freshness is Freshness.FRESH
    assert evidence.volume_trend_ratio == 1.2


def test_volume_fresh_for_stock_source_without_vendor_lock():
    evidence = SetupEvidenceBuilder().build(
        _candidate(),
        _setup_eval(),
        volume_trend_ratio=1.2,
        candle_source=None,
    )
    assert evidence.volume_freshness is Freshness.FRESH
    assert evidence.volume_trend_ratio == 1.2


def test_volume_missing_for_yahoo_inferred():
    evidence = SetupEvidenceBuilder().build(
        _candidate(),
        _setup_eval(),
        volume_trend_ratio=0.8,
        candle_source="yahoo_inferred",
    )
    assert evidence.volume_freshness is Freshness.MISSING
    assert evidence.volume_trend_ratio is None


def test_technical_fields_threaded():
    candidate = _candidate(
        trend="SIDE",
        rsi=48.0,
        bb_width_pctile=0.1,
        vwap_discount_pct=2.3,
        vwap_pct=-1.1,
    )
    evidence = SetupEvidenceBuilder().build(candidate, _setup_eval())
    assert evidence.trend == "SIDE"
    assert evidence.rsi == 48.0
    assert evidence.bb_width_pctile == 0.1
    assert evidence.vwap_discount_pct == 2.3
    assert evidence.vwap_pct == -1.1


def test_bb_width_pctile_bounds():
    with pytest.raises(ValueError):
        SetupEvidenceBuilder().build(
            _candidate(bb_width_pctile=1.5), _setup_eval()
        )


def test_no_setup_eval():
    evidence = SetupEvidenceBuilder().build(_candidate(), None)
    assert evidence.setup_name is None
    assert evidence.setup_match == "NO_MATCH"
    assert evidence.match_strength == 20.0
    assert evidence.failed_gates == ()


def test_freshness_fields_are_enum_instances():
    evidence = SetupEvidenceBuilder().build(_candidate(), _setup_eval())
    assert isinstance(evidence.rs_freshness, Freshness)
    assert isinstance(evidence.volume_freshness, Freshness)


def test_to_dict_serializes_freshness_as_string():
    evidence = SetupEvidenceBuilder().build(
        _candidate(),
        _setup_eval(match="PARTIAL"),
        rs_vs_ihsg_5d=0.3,
        analysis_date=date(2026, 1, 1),
        volume_trend_ratio=1.5,
        candle_source="stockbit",
    )
    d = evidence.to_dict()
    assert d["rs_freshness"] == "FRESH"
    assert d["volume_freshness"] == "FRESH"
    assert d["setup_match"] == "PARTIAL"
    assert d["match_strength"] == 60.0
    assert d["rs_vs_ihsg_5d"] == 0.3
    assert d["volume_trend_ratio"] == 1.5
    assert isinstance(d["snapshot_date"], str)
    assert isinstance(d["failed_gates"], list)
