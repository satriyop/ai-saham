"""
Tests for RegimeDetectionEvidence forward-label lifecycle and SQLite persistence.

Covers:
- Forward labels start as None
- SQLite save/get roundtrip fidelity
- update_forward_labels() fills only NULL slots (idempotent)
- update_forward_labels() does not overwrite existing values
- update_forward_labels() returns False for missing observation
- get_recent() returns newest-first
- regime_observations table has no ticker column
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from src.domain.value_objects.regime_detection_evidence import (
    RegimeDetectionEvidence,
    RegimeStability,
)
from src.infrastructure.persistence.sqlite_regime_observation_repository import (
    SQLiteRegimeObservationRepository,
)

# ── Helper ────────────────────────────────────────────────────────────────────


def _make_evidence(**kwargs) -> RegimeDetectionEvidence:
    defaults = dict(
        observation_date=date(2024, 1, 1),
        schema_version=1,
        regime="RISK_ON",
        regime_score=0.75,
        regime_confidence=0.8,
        regime_stability=RegimeStability.STABLE,
        days_in_regime=5,
        transition_warning=None,
        ihsg_20d_return=0.02,
        ihsg_trend_structure="ABOVE_BOTH",
        ihsg_breadth_pct_above_ma=65.0,
        ihsg_volume_trend=1.1,
        ihsg_atr_pct=0.8,
        idx_foreign_flow_5d=1_000_000_000.0,
        idx_foreign_flow_20d=5_000_000_000.0,
        foreign_buy_streak=3,
        foreign_sell_streak=0,
        banking_sector_vs_ihsg=0.5,
        sector_breadth=65.0,
    )
    defaults.update(kwargs)
    return RegimeDetectionEvidence(**defaults)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_forward_labels_initially_none():
    ev = _make_evidence()
    assert ev.forward_ihsg_return_5d is None
    assert ev.forward_ihsg_return_10d is None
    assert ev.forward_ihsg_return_20d is None


def test_sqlite_save_and_get_roundtrip(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    ev = _make_evidence()
    repo.save(ev)
    loaded = repo.get(ev.observation_date)
    assert loaded is not None
    assert loaded.observation_date == ev.observation_date
    assert loaded.regime == ev.regime
    assert loaded.regime_stability == ev.regime_stability
    assert loaded.ihsg_20d_return == pytest.approx(ev.ihsg_20d_return)


def test_update_forward_labels_fills_null_slots(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    ev = _make_evidence()
    repo.save(ev)
    result = repo.update_forward_labels(ev.observation_date, forward_ihsg_return_5d=0.05)
    assert result is True
    loaded = repo.get(ev.observation_date)
    assert loaded.forward_ihsg_return_5d == pytest.approx(0.05)
    assert loaded.forward_ihsg_return_10d is None  # untouched


def test_update_forward_labels_does_not_overwrite_existing(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    ev = _make_evidence(forward_ihsg_return_5d=0.125)
    repo.save(ev)
    repo.update_forward_labels(ev.observation_date, forward_ihsg_return_5d=99.9)
    loaded = repo.get(ev.observation_date)
    assert loaded.forward_ihsg_return_5d == pytest.approx(0.125)


def test_update_forward_labels_returns_false_for_missing_observation(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    result = repo.update_forward_labels(date(2024, 6, 1), forward_ihsg_return_5d=0.05)
    assert result is False


def test_get_recent_returns_newest_first(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    for d in [date(2024, 1, 1), date(2024, 1, 3), date(2024, 1, 2)]:
        repo.save(_make_evidence(observation_date=d))
    results = repo.get_recent(3)
    assert len(results) == 3
    assert results[0].observation_date == date(2024, 1, 3)
    assert results[1].observation_date == date(2024, 1, 2)
    assert results[2].observation_date == date(2024, 1, 1)


def test_no_ticker_column_in_table(tmp_path):
    _repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        column_names = {row[1] for row in conn.execute("PRAGMA table_info(regime_observations)")}
    assert "ticker" not in column_names
