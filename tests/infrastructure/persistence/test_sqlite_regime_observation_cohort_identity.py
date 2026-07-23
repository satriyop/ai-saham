"""Cohort-scoped persistence for regime_observations."""

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


def _make_evidence(**kwargs) -> RegimeDetectionEvidence:
    defaults = dict(
        observation_date=date(2024, 1, 15),
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


def test_two_cohorts_same_date_both_survive(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    d = date(2024, 1, 15)
    repo.save(_make_evidence(observation_date=d, semantic_compatibility_id="cohort-a", regime="RISK_ON"))
    repo.save(_make_evidence(observation_date=d, semantic_compatibility_id="cohort-b", regime="RISK_OFF"))

    a = repo.get(d, semantic_compatibility_id="cohort-a")
    b = repo.get(d, semantic_compatibility_id="cohort-b")
    assert a is not None and a.regime == "RISK_ON"
    assert b is not None and b.regime == "RISK_OFF"


def test_update_forward_labels_only_hits_one_cohort(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    d = date(2024, 1, 15)
    repo.save(_make_evidence(observation_date=d, semantic_compatibility_id="cohort-a"))
    repo.save(_make_evidence(observation_date=d, semantic_compatibility_id="cohort-b"))

    assert repo.update_forward_labels(
        d,
        forward_ihsg_return_5d=0.05,
        semantic_compatibility_id="cohort-a",
    )

    a = repo.get(d, semantic_compatibility_id="cohort-a")
    b = repo.get(d, semantic_compatibility_id="cohort-b")
    assert a is not None and a.forward_ihsg_return_5d == pytest.approx(0.05)
    assert b is not None and b.forward_ihsg_return_5d is None


def test_get_without_cohort_ambiguous_when_two_rows(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    d = date(2024, 1, 15)
    repo.save(_make_evidence(observation_date=d, semantic_compatibility_id="cohort-a"))
    repo.save(_make_evidence(observation_date=d, semantic_compatibility_id="cohort-b"))
    assert repo.get(d) is None


def test_get_without_cohort_returns_single_legacy_row(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    d = date(2024, 1, 15)
    ev = _make_evidence(observation_date=d)
    repo.save(ev)
    loaded = repo.get(d)
    assert loaded is not None
    assert loaded.semantic_compatibility_id == ""


def test_cohort_fields_round_trip(tmp_path):
    repo = SQLiteRegimeObservationRepository(tmp_path / "test.db")
    ev = _make_evidence(
        semantic_compatibility_id="sha256:abc",
        observation_contract="market-context-regime",
        universe_name="lq45",
        benchmark_ticker="IHSG",
    )
    repo.save(ev)
    loaded = repo.get(ev.observation_date, semantic_compatibility_id="sha256:abc")
    assert loaded is not None
    assert loaded.semantic_compatibility_id == "sha256:abc"
    assert loaded.observation_contract == "market-context-regime"
    assert loaded.universe_name == "lq45"
    assert loaded.benchmark_ticker == "IHSG"


def test_legacy_schema_migrates_with_empty_cohort(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE regime_observations (
                observation_date TEXT NOT NULL PRIMARY KEY,
                schema_version INTEGER NOT NULL DEFAULT 1,
                regime TEXT NOT NULL,
                regime_score REAL NOT NULL,
                regime_confidence REAL NOT NULL,
                regime_stability TEXT NOT NULL,
                days_in_regime INTEGER,
                transition_warning TEXT,
                detection_inputs_json TEXT NOT NULL,
                forward_ihsg_return_5d REAL,
                forward_ihsg_return_10d REAL,
                forward_ihsg_return_20d REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO regime_observations VALUES
            ('2024-01-01', 1, 'RISK_ON', 0.7, 0.8, 'STABLE', 3, NULL,
             '{}', NULL, NULL, NULL, '2024-01-01T00:00:00', '2024-01-01T00:00:00')
            """
        )
        conn.commit()

    repo = SQLiteRegimeObservationRepository(db_path)
    loaded = repo.get(date(2024, 1, 1))
    assert loaded is not None
    assert loaded.regime == "RISK_ON"
    assert loaded.semantic_compatibility_id == ""

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(regime_observations)")}
    assert "semantic_compatibility_id" in columns
