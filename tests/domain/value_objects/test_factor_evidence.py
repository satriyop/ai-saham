"""Tests for FactorEvidence and SignalEvidence value objects (Phase 1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from src.domain.value_objects.factor_evidence import (
    Direction,
    FactorEvidence,
    Freshness,
    Horizon,
)
from src.domain.value_objects.signal_evidence import SignalEvidence


def _factor(
    name: str = "bandar_intensity",
    *,
    direction: Direction = Direction.BULLISH,
    strength: float = 0.66,
    confidence: float = 1.0,
    freshness: Freshness = Freshness.FRESH,
) -> FactorEvidence:
    return FactorEvidence(
        name=name,
        group="flow_confirmation",
        direction=direction,
        strength=strength,
        confidence=confidence,
        freshness=freshness,
        horizon=Horizon.DAILY,
        source="bandar_detector",
        rationale="broad_score=4/12 → 66.7/100",
        raw_fields=(("broad_score", "4"), ("max_range", "12")),
    )


def test_valid_factor_evidence():
    fe = _factor()
    assert fe.name == "bandar_intensity"
    assert fe.group == "flow_confirmation"
    assert fe.direction is Direction.BULLISH
    assert fe.strength == 0.66
    assert fe.confidence == 1.0
    assert fe.freshness is Freshness.FRESH
    assert fe.horizon is Horizon.DAILY
    assert fe.source == "bandar_detector"
    assert fe.rationale == "broad_score=4/12 → 66.7/100"
    assert fe.raw_fields == (("broad_score", "4"), ("max_range", "12"))


def test_strength_bounds():
    with pytest.raises(ValueError):
        _factor(strength=1.5)
    with pytest.raises(ValueError):
        _factor(strength=-0.1)


def test_confidence_bounds():
    with pytest.raises(ValueError):
        _factor(confidence=1.5)


def test_raw_fields_must_be_string_tuples():
    with pytest.raises(ValueError):
        FactorEvidence(
            name="x",
            group="context",
            direction=Direction.NEUTRAL,
            strength=0.5,
            confidence=1.0,
            freshness=Freshness.FRESH,
            horizon=Horizon.DAILY,
            source="s",
            rationale="r",
            raw_fields=(("k", 4),),  # value not a string
        )


def test_frozen_immutable():
    fe = _factor()
    with pytest.raises(FrozenInstanceError):
        fe.strength = 0.9  # type: ignore[misc]


def test_signal_evidence_aggregate_confidence():
    present = tuple(
        _factor(name=f"p{i}", freshness=Freshness.FRESH, confidence=1.0) for i in range(3)
    )
    missing = tuple(
        _factor(
            name=f"m{i}",
            freshness=Freshness.MISSING,
            confidence=0.0,
            direction=Direction.NEUTRAL,
            strength=0.5,
        )
        for i in range(3)
    )
    factors = present + missing
    ev = SignalEvidence(
        ticker="TEST",
        snapshot_date=date.today(),
        factors=factors,
        aggregate_confidence=1.0,
        coverage_ratio=0.5,
        missing_factors=tuple(f.name for f in missing),
    )
    assert ev.aggregate_confidence == 1.0
    assert ev.coverage_ratio == 0.5


def test_signal_evidence_all_missing():
    ev = SignalEvidence(
        ticker="TEST",
        snapshot_date=date.today(),
        factors=(),
        aggregate_confidence=0.0,
        coverage_ratio=0.0,
        missing_factors=(),
    )
    assert ev.aggregate_confidence == 0.0
    assert ev.coverage_ratio == 0.0


def test_signal_evidence_coverage_ratio_bounds():
    with pytest.raises(ValueError):
        SignalEvidence(
            ticker="TEST",
            snapshot_date=date.today(),
            factors=(),
            aggregate_confidence=0.0,
            coverage_ratio=1.5,
            missing_factors=(),
        )
    with pytest.raises(ValueError):
        SignalEvidence(
            ticker="TEST",
            snapshot_date=date.today(),
            factors=(),
            aggregate_confidence=1.5,
            coverage_ratio=0.5,
            missing_factors=(),
        )


# ── from_dict / to_dict round-trip and schema-evolution tolerance ─────────────


def test_factor_evidence_round_trip():
    fe = _factor()
    assert FactorEvidence.from_dict(fe.to_dict()) == fe


def test_factor_evidence_from_dict_unknown_enum_falls_back_to_default():
    data = _factor().to_dict()
    data["direction"] = "SIDEWAYS"  # unknown Direction value
    data["freshness"] = "EXPIRED"  # unknown Freshness value
    data["horizon"] = "DECADAL"  # unknown Horizon value
    parsed = FactorEvidence.from_dict(data)
    assert parsed.direction == Direction.NEUTRAL
    assert parsed.freshness == Freshness.MISSING
    assert parsed.horizon == Horizon.DAILY


def test_factor_evidence_from_dict_missing_optional_fields():
    minimal = {"name": "bandar_intensity"}
    parsed = FactorEvidence.from_dict(minimal)
    assert parsed.name == "bandar_intensity"
    assert parsed.strength == 0.0
    assert parsed.confidence == 0.0
    assert parsed.rationale == ""
    assert parsed.raw_fields == ()


def test_signal_evidence_round_trip():
    se = SignalEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 4),
        factors=(_factor("bandar_intensity"), _factor("foreign_flow_quality")),
        aggregate_confidence=1.0,
        coverage_ratio=1.0,
        missing_factors=(),
    )
    restored = SignalEvidence.from_dict(se.to_dict())
    assert restored.ticker == se.ticker
    assert restored.snapshot_date == se.snapshot_date
    assert len(restored.factors) == 2
    assert restored.factors[0] == se.factors[0]
    assert restored.aggregate_confidence == se.aggregate_confidence
    assert restored.coverage_ratio == se.coverage_ratio


def test_signal_evidence_to_dict_includes_schema_version():
    se = SignalEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 4),
        factors=(),
        aggregate_confidence=0.0,
        coverage_ratio=0.0,
        missing_factors=(),
    )
    assert se.to_dict()["schema_version"] == 1


def test_signal_evidence_from_dict_rejects_future_schema_version():
    se = SignalEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 4),
        factors=(),
        aggregate_confidence=0.0,
        coverage_ratio=0.0,
        missing_factors=(),
    )
    payload = se.to_dict()
    payload["schema_version"] = 99
    with pytest.raises(ValueError, match="schema_version 99 is not supported"):
        SignalEvidence.from_dict(payload)


def test_signal_evidence_from_dict_missing_optional_fields_default_safely():
    payload = {
        "ticker": "BBRI",
        "snapshot_date": "2026-07-04",
        # factors, aggregate_confidence, coverage_ratio, missing_factors all absent
    }
    se = SignalEvidence.from_dict(payload)
    assert se.ticker == "BBRI"
    assert se.factors == ()
    assert se.aggregate_confidence == 0.0
    assert se.coverage_ratio == 0.0
    assert se.missing_factors == ()
