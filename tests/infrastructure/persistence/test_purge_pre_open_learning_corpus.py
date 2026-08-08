"""Purpose isolation for PRE_OPEN clean-break purge."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.infrastructure.persistence.purge_pre_open_learning_corpus import (
    purge_pre_open_learning_corpus,
)


def _seed(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE learning_observations (
            observation_id TEXT PRIMARY KEY,
            purpose TEXT NOT NULL,
            compatibility_id TEXT NOT NULL
        );
        CREATE TABLE learning_outcome_labels (
            label_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL,
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
        """
    )
    con.execute(
        "INSERT INTO learning_observations VALUES (?,?,?)",
        ("po1", "PRE_OPEN_AUCTION_DIRECTION", "sha256:pre"),
    )
    con.execute(
        "INSERT INTO learning_observations VALUES (?,?,?)",
        ("ac1", "ACCUMULATION_DISCOVERY", "sha256:accum"),
    )
    con.execute("INSERT INTO learning_outcome_labels VALUES (?,?)", ("l1", "po1"))
    con.execute("INSERT INTO learning_outcome_labels VALUES (?,?)", ("l2", "ac1"))
    con.execute(
        "INSERT INTO learning_evaluations VALUES (?,?)",
        ("e1", "PRE_OPEN_AUCTION_DIRECTION"),
    )
    con.commit()
    con.close()


def test_pre_open_purge_preserves_accum(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    _seed(path)
    dry = purge_pre_open_learning_corpus(path, execute=False)
    assert dry.counts.preopen_observations == 1
    assert dry.counts.accum_observations == 1
    report = purge_pre_open_learning_corpus(path, execute=True)
    assert report.executed is True
    con = sqlite3.connect(path)
    assert (
        con.execute(
            "SELECT COUNT(*) FROM learning_observations WHERE purpose='PRE_OPEN_AUCTION_DIRECTION'"
        ).fetchone()[0]
        == 0
    )
    assert (
        con.execute(
            "SELECT COUNT(*) FROM learning_observations WHERE purpose='ACCUMULATION_DISCOVERY'"
        ).fetchone()[0]
        == 1
    )
    assert con.execute("SELECT COUNT(*) FROM learning_outcome_labels").fetchone()[0] == 1
    assert con.execute("SELECT observation_id FROM learning_outcome_labels").fetchone()[0] == "ac1"
    con.close()
