"""Tests for the TickerProfileSnapshot domain value object (Phase F)."""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot


def _snapshot(**overrides) -> TickerProfileSnapshot:
    defaults = dict(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        epoch="2026-07",
        primary_profile="foreign_institutional",
        profile_confidence=0.8,
        liquidity_score=0.9,
        broker_concentration_score=0.3,
        foreign_flow_score=0.4,
        volatility_score=0.2,
        index_membership_score=1.0,
        market_cap_bucket="large",
        sector="Financials",
        sub_sector="Banks",
        index_memberships=("lq45", "idx80"),
        coverage_score=1.0,
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=("in lq45",),
        unavailable_reasons=(),
        market_tier="blue_chip",
        foreign_institutional_exposure=0.75,
        domestic_bandar_exposure=0.20,
        retail_speculative_exposure=0.05,
        metadata={"diagnostic_only": True},
    )
    defaults.update(overrides)
    return TickerProfileSnapshot(**defaults)  # type: ignore[arg-type]


def test_snapshot_round_trip():
    snapshot = _snapshot()
    assert TickerProfileSnapshot.from_dict(snapshot.to_dict()) == snapshot


def test_snapshot_serializes_date_as_iso_string():
    snapshot = _snapshot()
    assert snapshot.to_dict()["snapshot_date"] == "2026-07-01"


def test_from_dict_accepts_date_object():
    payload = _snapshot().to_dict()
    payload["snapshot_date"] = date(2026, 7, 1)
    restored = TickerProfileSnapshot.from_dict(payload)
    assert restored.snapshot_date == date(2026, 7, 1)


def test_snapshot_rejects_empty_ticker():
    with pytest.raises(ValueError):
        _snapshot(ticker="")


@pytest.mark.parametrize("bad_value", [-0.1, 1.1])
def test_snapshot_rejects_out_of_bounds_score(bad_value):
    with pytest.raises(ValueError):
        _snapshot(liquidity_score=bad_value)


@pytest.mark.parametrize(
    "field_name",
    [
        "foreign_institutional_exposure",
        "domestic_bandar_exposure",
        "retail_speculative_exposure",
    ],
)
@pytest.mark.parametrize("bad_value", [-0.1, 1.1])
def test_snapshot_rejects_out_of_bounds_exposure(field_name, bad_value):
    with pytest.raises(ValueError):
        _snapshot(**{field_name: bad_value})


def test_from_dict_accepts_legacy_profile_label_key():
    # Back-compat: older payloads persisted "profile_label" instead of
    # "primary_profile". from_dict must still populate primary_profile.
    restored = TickerProfileSnapshot.from_dict(
        {
            "ticker": "BBCA",
            "snapshot_date": "2026-07-01",
            "profile_label": "foreign_institutional",
        }
    )
    assert restored.primary_profile == "foreign_institutional"


def test_from_dict_accepts_minimal_dict():
    snapshot = TickerProfileSnapshot.from_dict(
        {"ticker": "bbca", "snapshot_date": "2026-07-01"}
    )
    assert snapshot.ticker == "BBCA"
    assert snapshot.snapshot_date == date(2026, 7, 1)
    assert snapshot.primary_profile == "unknown"
    assert snapshot.profile_confidence == 0.0
    assert snapshot.coverage_score == 0.0
    assert snapshot.evidence_status is EvidenceStatus.DIAGNOSTIC
    assert snapshot.index_memberships == ()
    assert snapshot.market_tier is None
    assert snapshot.foreign_institutional_exposure is None
    assert snapshot.domestic_bandar_exposure is None
    assert snapshot.retail_speculative_exposure is None
    assert snapshot.metadata == {}


def test_from_dict_returns_none_for_missing_optional_scores():
    snapshot = TickerProfileSnapshot.from_dict(
        {"ticker": "BBCA", "snapshot_date": "2026-07-01"}
    )
    assert snapshot.liquidity_score is None
    assert snapshot.broker_concentration_score is None
    assert snapshot.foreign_flow_score is None
    assert snapshot.volatility_score is None
    assert snapshot.index_membership_score is None
    assert snapshot.market_cap_bucket is None
