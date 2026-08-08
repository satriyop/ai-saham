"""Unit tests for accum corpus purge blast radius and purpose isolation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.persistence.purge_accum_learning_corpus import (
    purge_accum_learning_corpus,
)


def _create_schema(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE learning_observations (
            observation_id TEXT PRIMARY KEY,
            purpose TEXT NOT NULL,
            compatibility_id TEXT NOT NULL,
            decision_payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE learning_outcome_labels (
            label_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL,
            contract_id TEXT NOT NULL,
            FOREIGN KEY (observation_id) REFERENCES learning_observations(observation_id)
                ON DELETE RESTRICT
        );
        CREATE TABLE learning_track_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL,
            FOREIGN KEY (observation_id) REFERENCES learning_observations(observation_id)
                ON DELETE RESTRICT
        );
        CREATE TABLE learning_evaluations (
            evaluation_id TEXT PRIMARY KEY,
            purpose TEXT NOT NULL
        );
        CREATE TABLE learning_policy_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            purpose TEXT NOT NULL,
            compatibility_id TEXT NOT NULL,
            policy_id TEXT NOT NULL
        );
        CREATE TABLE setup_phase_ledger (
            entry_id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            as_of_date TEXT NOT NULL
        );
        """
    )
    con.commit()
    con.close()


def _seed(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    # Accum cohort
    con.execute(
        "INSERT INTO learning_observations VALUES (?,?,?,?)",
        ("obs-a1", "ACCUMULATION_DISCOVERY", "sha256:aaa", "{}"),
    )
    con.execute(
        "INSERT INTO learning_observations VALUES (?,?,?,?)",
        ("obs-a2", "ACCUMULATION_DISCOVERY", "sha256:bbb", "{}"),
    )
    con.execute(
        "INSERT INTO learning_outcome_labels VALUES (?,?,?)",
        ("lab-a1", "obs-a1", "price_path.accum_10d.v1"),
    )
    con.execute(
        "INSERT INTO learning_outcome_labels VALUES (?,?,?)",
        ("lab-a2", "obs-a2", "price_path.accum_10d.v1"),
    )
    con.execute(
        "INSERT INTO learning_track_snapshots VALUES (?,?)",
        ("trk-a1", "obs-a1"),
    )
    con.execute(
        "INSERT INTO learning_evaluations VALUES (?,?)",
        ("ev-a1", "ACCUMULATION_DISCOVERY"),
    )
    con.execute(
        "INSERT INTO learning_policy_snapshots VALUES (?,?,?,?)",
        ("snap-a1", "ACCUMULATION_DISCOVERY", "sha256:aaa", "screener.accum.score_weights"),
    )
    con.execute(
        "INSERT INTO learning_policy_snapshots VALUES (?,?,?,?)",
        ("snap-a2", "ACCUMULATION_DISCOVERY", "sha256:bbb", "risk.accum.hard_gates"),
    )
    # PRE_OPEN isolation control
    con.execute(
        "INSERT INTO learning_observations VALUES (?,?,?,?)",
        ("obs-p1", "PRE_OPEN_AUCTION_DIRECTION", "sha256:pre", "{}"),
    )
    con.execute(
        "INSERT INTO learning_outcome_labels VALUES (?,?,?)",
        ("lab-p1", "obs-p1", "pre_open.session.v1"),
    )
    # Phase ledger (full clear on purge)
    con.execute(
        "INSERT INTO setup_phase_ledger VALUES (?,?,?)",
        ("ph1", "BBCA", "2026-08-01"),
    )
    con.execute(
        "INSERT INTO setup_phase_ledger VALUES (?,?,?)",
        ("ph2", "BBRI", "2026-08-02"),
    )
    con.commit()
    con.close()


def test_dry_run_does_not_delete(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    _create_schema(path)
    _seed(path)

    report = purge_accum_learning_corpus(path, execute=False)
    assert report.executed is False
    assert report.counts.accum_observations == 2
    assert report.counts.labels == 2
    assert report.counts.track_snapshots == 1
    assert report.counts.evaluations == 1
    assert report.counts.policy_snapshots == 2
    assert report.counts.phase_ledger_rows == 2
    assert report.counts.non_accum_observations == 1
    assert report.counts.preopen_labels == 1

    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM learning_observations").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM setup_phase_ledger").fetchone()[0] == 2
    con.close()


def test_execute_deletes_accum_preserves_preopen(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    _create_schema(path)
    _seed(path)

    before = purge_accum_learning_corpus(path, execute=False)
    after = purge_accum_learning_corpus(path, execute=True)
    assert after.executed is True
    assert after.counts == before.counts
    assert after.foreign_key_violations == 0

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    accum_left = con.execute(
        "SELECT COUNT(*) FROM learning_observations WHERE purpose = 'ACCUMULATION_DISCOVERY'"
    ).fetchone()[0]
    assert accum_left == 0
    preopen_left = con.execute(
        "SELECT COUNT(*) FROM learning_observations WHERE purpose = 'PRE_OPEN_AUCTION_DIRECTION'"
    ).fetchone()[0]
    assert preopen_left == 1
    assert con.execute("SELECT COUNT(*) FROM learning_outcome_labels").fetchone()[0] == 1
    assert (
        con.execute("SELECT observation_id FROM learning_outcome_labels").fetchone()[0] == "obs-p1"
    )
    assert con.execute("SELECT COUNT(*) FROM learning_track_snapshots").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM learning_evaluations").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM learning_policy_snapshots").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM setup_phase_ledger").fetchone()[0] == 0
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def test_dry_run_and_execute_counts_match(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    _create_schema(path)
    _seed(path)
    dry = purge_accum_learning_corpus(path, execute=False)
    report = purge_accum_learning_corpus(path, execute=True)
    assert report.counts == dry.counts
    assert report.executed is True


def test_execute_fails_closed_if_restrict_child_not_deleted(tmp_path: Path, monkeypatch) -> None:
    """If a RESTRICT child remains, the transaction must not commit half-deleted."""
    path = tmp_path / "t.db"
    _create_schema(path)
    _seed(path)

    from src.infrastructure.persistence import purge_accum_learning_corpus as mod

    real_delete = mod._delete_in

    def skip_labels(con, table, column, ids):
        if table == "learning_outcome_labels":
            return 0
        return real_delete(con, table, column, ids)

    monkeypatch.setattr(mod, "_delete_in", skip_labels)

    with pytest.raises(sqlite3.IntegrityError):
        purge_accum_learning_corpus(path, execute=True)

    # Rolled back: accum rows still present
    con = sqlite3.connect(path)
    assert (
        con.execute(
            "SELECT COUNT(*) FROM learning_observations WHERE purpose='ACCUMULATION_DISCOVERY'"
        ).fetchone()[0]
        == 2
    )
    con.close()
