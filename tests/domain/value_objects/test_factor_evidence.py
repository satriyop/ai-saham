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
        _factor(name=f"p{i}", freshness=Freshness.FRESH, confidence=1.0)
        for i in range(3)
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
