"""Unit tests for the canonical swing effective-session contract.

Layer: Test (domain unit)
"""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.value_objects.canonical_swing_session_contract import (
    CanonicalSwingSessionContract,
)


def test_contract_accepts_three_equal_dates():
    session = date(2026, 7, 1)
    contract = CanonicalSwingSessionContract(
        snapshot_date=session,
        latest_completed_session=session,
        analysis_as_of=session,
    )
    assert contract.snapshot_date == session
    assert contract.latest_completed_session == session
    assert contract.analysis_as_of == session


def test_contract_rejects_snapshot_date_ahead_of_latest_completed_session():
    snapshot = date(2026, 7, 2)
    latest = date(2026, 7, 1)
    with pytest.raises(ValueError, match="snapshot_date .* must equal latest_completed_session"):
        CanonicalSwingSessionContract(
            snapshot_date=snapshot,
            latest_completed_session=latest,
            analysis_as_of=snapshot,
        )


def test_contract_rejects_snapshot_date_ahead_of_analysis_as_of():
    snapshot = date(2026, 7, 2)
    as_of = date(2026, 7, 1)
    with pytest.raises(ValueError, match="snapshot_date .* must equal analysis_as_of"):
        CanonicalSwingSessionContract(
            snapshot_date=snapshot,
            latest_completed_session=snapshot,
            analysis_as_of=as_of,
        )


def test_contract_rejects_latest_completed_session_behind_analysis_as_of():
    latest = date(2026, 6, 30)
    as_of = date(2026, 7, 1)
    with pytest.raises(ValueError, match="snapshot_date .* must equal latest_completed_session"):
        CanonicalSwingSessionContract(
            snapshot_date=as_of,
            latest_completed_session=latest,
            analysis_as_of=as_of,
        )


def test_from_observation_fields_raises_when_latest_completed_session_missing():
    with pytest.raises(ValueError, match="non-None latest_completed_session"):
        CanonicalSwingSessionContract.from_observation_fields(
            snapshot_date=date(2026, 7, 1),
            latest_completed_session=None,
            analysis_as_of=date(2026, 7, 1),
        )


def test_from_observation_fields_raises_when_analysis_as_of_missing():
    with pytest.raises(ValueError, match="non-None latest_completed_session"):
        CanonicalSwingSessionContract.from_observation_fields(
            snapshot_date=date(2026, 7, 1),
            latest_completed_session=date(2026, 7, 1),
            analysis_as_of=None,
        )


def test_from_observation_fields_raises_on_date_mismatch():
    with pytest.raises(ValueError, match="snapshot_date .* must equal latest_completed_session"):
        CanonicalSwingSessionContract.from_observation_fields(
            snapshot_date=date(2026, 7, 2),
            latest_completed_session=date(2026, 7, 1),
            analysis_as_of=date(2026, 7, 2),
        )


def test_from_observation_fields_builds_contract_when_all_equal():
    session = date(2026, 7, 1)
    contract = CanonicalSwingSessionContract.from_observation_fields(
        snapshot_date=session,
        latest_completed_session=session,
        analysis_as_of=session,
    )
    assert contract.snapshot_date == session
    assert contract.latest_completed_session == session
    assert contract.analysis_as_of == session
