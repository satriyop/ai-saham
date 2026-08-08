"""FK-safe purge of PRE_OPEN_AUCTION_DIRECTION learning rows only.

Layer: Infrastructure. Does **not** touch ACCUMULATION_DISCOVERY, phase ledger,
or market data. Used for pre-open score identity clean breaks (task 05).
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.infrastructure.persistence.purge_accum_learning_corpus import (
    _count_in,
    _delete_in,
    _table_exists,
    connect_purge_db,
)

PRE_OPEN_PURPOSE = "PRE_OPEN_AUCTION_DIRECTION"
ACCUM_PURPOSE = "ACCUMULATION_DISCOVERY"


@dataclass(frozen=True)
class PreOpenPurgeCounts:
    preopen_observations: int
    track_snapshots: int
    labels: int
    evaluations: int
    accum_observations: int

    def to_dict(self) -> dict[str, int]:
        return {k: int(v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class PreOpenPurgeReport:
    db_path: str
    counts: PreOpenPurgeCounts
    executed: bool
    foreign_key_violations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "db_path": self.db_path,
            "executed": self.executed,
            "counts": self.counts.to_dict(),
            "foreign_key_violations": self.foreign_key_violations,
        }


def _preopen_ids(con: sqlite3.Connection) -> list[str]:
    if not _table_exists(con, "learning_observations"):
        return []
    return [
        str(r["observation_id"])
        for r in con.execute(
            "SELECT observation_id FROM learning_observations WHERE purpose = ?",
            (PRE_OPEN_PURPOSE,),
        )
    ]


def measure_pre_open_purge_blast_radius(con: sqlite3.Connection) -> PreOpenPurgeCounts:
    ids = _preopen_ids(con)
    n_eval = 0
    if _table_exists(con, "learning_evaluations"):
        n_eval = int(
            con.execute(
                "SELECT COUNT(*) AS c FROM learning_evaluations WHERE purpose = ?",
                (PRE_OPEN_PURPOSE,),
            ).fetchone()["c"]
        )
    n_accum = 0
    if _table_exists(con, "learning_observations"):
        n_accum = int(
            con.execute(
                "SELECT COUNT(*) AS c FROM learning_observations WHERE purpose = ?",
                (ACCUM_PURPOSE,),
            ).fetchone()["c"]
        )
    return PreOpenPurgeCounts(
        preopen_observations=len(ids),
        track_snapshots=_count_in(con, "learning_track_snapshots", "observation_id", ids),
        labels=_count_in(con, "learning_outcome_labels", "observation_id", ids),
        evaluations=n_eval,
        accum_observations=n_accum,
    )


def execute_pre_open_purge(con: sqlite3.Connection) -> PreOpenPurgeCounts:
    before = measure_pre_open_purge_blast_radius(con)
    ids = _preopen_ids(con)
    _delete_in(con, "learning_track_snapshots", "observation_id", ids)
    _delete_in(con, "learning_outcome_labels", "observation_id", ids)
    if _table_exists(con, "learning_evaluations"):
        con.execute(
            "DELETE FROM learning_evaluations WHERE purpose = ?",
            (PRE_OPEN_PURPOSE,),
        )
    if _table_exists(con, "learning_observations"):
        con.execute(
            "DELETE FROM learning_observations WHERE purpose = ?",
            (PRE_OPEN_PURPOSE,),
        )
    return before


def purge_pre_open_learning_corpus(db_path: Path, *, execute: bool) -> PreOpenPurgeReport:
    path = Path(db_path)
    con = connect_purge_db(path)
    try:
        if not execute:
            return PreOpenPurgeReport(
                db_path=str(path),
                counts=measure_pre_open_purge_blast_radius(con),
                executed=False,
            )
        con.execute("BEGIN IMMEDIATE")
        try:
            counts = execute_pre_open_purge(con)
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            if fk:
                con.rollback()
                return PreOpenPurgeReport(
                    db_path=str(path),
                    counts=counts,
                    executed=False,
                    foreign_key_violations=len(fk),
                )
            after = measure_pre_open_purge_blast_radius(con)
            if after.preopen_observations != 0:
                con.rollback()
                raise RuntimeError("pre-open purge postcondition failed: rows remain")
            if after.accum_observations != counts.accum_observations:
                con.rollback()
                raise RuntimeError(
                    "pre-open purge postcondition failed: accum observation count changed"
                )
            con.commit()
            return PreOpenPurgeReport(
                db_path=str(path),
                counts=counts,
                executed=True,
            )
        except Exception:
            con.rollback()
            raise
    finally:
        con.close()
