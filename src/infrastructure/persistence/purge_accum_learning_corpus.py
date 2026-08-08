"""FK-safe purge of ACCUMULATION_DISCOVERY learning corpus for clean-break rebuild.

Layer: Infrastructure (SQLite ops). Application owns when to call; this module
only counts and deletes the approved tables.

Deletes (execute order):
1. ``learning_track_snapshots`` for accum observation_ids (RESTRICT children)
2. ``learning_outcome_labels`` for accum observation_ids (RESTRICT children)
3. ``learning_evaluations`` where purpose = ACCUMULATION_DISCOVERY
4. ``learning_observations`` where purpose = ACCUMULATION_DISCOVERY
5. ``learning_policy_snapshots`` where purpose = ACCUMULATION_DISCOVERY
6. ``setup_phase_ledger`` — full table (rebuild via observation backfill)

Does **not** touch PRE_OPEN / SWING observations or their labels, market data,
or diagnostic-producer snapshots (empty today; purpose-isolated if added).
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ACCUM_PURPOSE = "ACCUMULATION_DISCOVERY"


@dataclass(frozen=True)
class AccumPurgeCounts:
    """Blast-radius counters (dry-run and post-execute)."""

    accum_observations: int
    track_snapshots: int
    labels: int
    evaluations: int
    policy_snapshots: int
    phase_ledger_rows: int
    non_accum_observations: int
    preopen_labels: int

    def to_dict(self) -> dict[str, int]:
        return {k: int(v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class AccumPurgeReport:
    db_path: str
    counts: AccumPurgeCounts
    executed: bool
    foreign_key_violations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "db_path": self.db_path,
            "executed": self.executed,
            "counts": self.counts.to_dict(),
            "foreign_key_violations": self.foreign_key_violations,
        }


def connect_purge_db(db_path: Path) -> sqlite3.Connection:
    """Open SQLite with mandatory foreign-key enforcement."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    enabled = con.execute("PRAGMA foreign_keys").fetchone()[0]
    if enabled != 1:
        con.close()
        raise RuntimeError("SQLite foreign key enforcement is required")
    return con


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _accum_observation_ids(con: sqlite3.Connection) -> list[str]:
    if not _table_exists(con, "learning_observations"):
        return []
    return [
        str(r["observation_id"])
        for r in con.execute(
            "SELECT observation_id FROM learning_observations WHERE purpose = ?",
            (ACCUM_PURPOSE,),
        )
    ]


def _count_in(con: sqlite3.Connection, table: str, column: str, ids: list[str]) -> int:
    if not ids or not _table_exists(con, table):
        return 0
    # Chunk to stay under SQLite variable limits on large corpora.
    total = 0
    chunk = 400
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        placeholders = ",".join("?" * len(part))
        total += int(
            con.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {column} IN ({placeholders})",
                part,
            ).fetchone()["c"]
        )
    return total


def measure_accum_purge_blast_radius(con: sqlite3.Connection) -> AccumPurgeCounts:
    """Count every row the purge would delete (and the PRE_OPEN control)."""
    obs_ids = _accum_observation_ids(con)

    n_obs = len(obs_ids)
    n_tracks = _count_in(con, "learning_track_snapshots", "observation_id", obs_ids)
    n_labels = _count_in(con, "learning_outcome_labels", "observation_id", obs_ids)

    n_eval = 0
    if _table_exists(con, "learning_evaluations"):
        n_eval = int(
            con.execute(
                "SELECT COUNT(*) AS c FROM learning_evaluations WHERE purpose = ?",
                (ACCUM_PURPOSE,),
            ).fetchone()["c"]
        )

    n_snaps = 0
    if _table_exists(con, "learning_policy_snapshots"):
        n_snaps = int(
            con.execute(
                "SELECT COUNT(*) AS c FROM learning_policy_snapshots WHERE purpose = ?",
                (ACCUM_PURPOSE,),
            ).fetchone()["c"]
        )

    n_phase = 0
    if _table_exists(con, "setup_phase_ledger"):
        n_phase = int(con.execute("SELECT COUNT(*) AS c FROM setup_phase_ledger").fetchone()["c"])

    n_non_accum = 0
    if _table_exists(con, "learning_observations"):
        n_non_accum = int(
            con.execute(
                "SELECT COUNT(*) AS c FROM learning_observations WHERE purpose != ?",
                (ACCUM_PURPOSE,),
            ).fetchone()["c"]
        )

    # Labels for non-accum obs must remain after purge (isolation control).
    non_accum_ids = []
    if _table_exists(con, "learning_observations"):
        non_accum_ids = [
            str(r["observation_id"])
            for r in con.execute(
                "SELECT observation_id FROM learning_observations WHERE purpose != ?",
                (ACCUM_PURPOSE,),
            )
        ]
    n_preopen_labels = _count_in(con, "learning_outcome_labels", "observation_id", non_accum_ids)

    return AccumPurgeCounts(
        accum_observations=n_obs,
        track_snapshots=n_tracks,
        labels=n_labels,
        evaluations=n_eval,
        policy_snapshots=n_snaps,
        phase_ledger_rows=n_phase,
        non_accum_observations=n_non_accum,
        preopen_labels=n_preopen_labels,
    )


def _delete_in(con: sqlite3.Connection, table: str, column: str, ids: list[str]) -> int:
    if not ids or not _table_exists(con, table):
        return 0
    deleted = 0
    chunk = 400
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        placeholders = ",".join("?" * len(part))
        cur = con.execute(
            f"DELETE FROM {table} WHERE {column} IN ({placeholders})",
            part,
        )
        deleted += int(cur.rowcount or 0)
    return deleted


def execute_accum_purge(con: sqlite3.Connection) -> AccumPurgeCounts:
    """Delete the measured blast radius inside the caller's transaction scope.

    Caller must BEGIN/COMMIT. Returns pre-delete counts for the report.
    """
    before = measure_accum_purge_blast_radius(con)
    obs_ids = _accum_observation_ids(con)

    # RESTRICT children first.
    _delete_in(con, "learning_track_snapshots", "observation_id", obs_ids)
    _delete_in(con, "learning_outcome_labels", "observation_id", obs_ids)

    if _table_exists(con, "learning_evaluations"):
        con.execute(
            "DELETE FROM learning_evaluations WHERE purpose = ?",
            (ACCUM_PURPOSE,),
        )
    if _table_exists(con, "learning_observations"):
        con.execute(
            "DELETE FROM learning_observations WHERE purpose = ?",
            (ACCUM_PURPOSE,),
        )
    if _table_exists(con, "learning_policy_snapshots"):
        con.execute(
            "DELETE FROM learning_policy_snapshots WHERE purpose = ?",
            (ACCUM_PURPOSE,),
        )
    # Full ledger clear: post-rebuild ``backfill-phase-ledger`` repopulates from
    # new schema-15 observations. Pre-batch phase memory is not comparable.
    if _table_exists(con, "setup_phase_ledger"):
        con.execute("DELETE FROM setup_phase_ledger")

    return before


def purge_accum_learning_corpus(db_path: Path, *, execute: bool) -> AccumPurgeReport:
    """Dry-run or execute the accum corpus purge against one SQLite file."""
    path = Path(db_path)
    con = connect_purge_db(path)
    try:
        if not execute:
            counts = measure_accum_purge_blast_radius(con)
            return AccumPurgeReport(
                db_path=str(path),
                counts=counts,
                executed=False,
                foreign_key_violations=0,
            )

        con.execute("BEGIN IMMEDIATE")
        try:
            counts = execute_accum_purge(con)
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            if fk:
                con.rollback()
                return AccumPurgeReport(
                    db_path=str(path),
                    counts=counts,
                    executed=False,
                    foreign_key_violations=len(fk),
                )
            # Postcondition: zero accum obs / snapshots; PRE_OPEN preserved.
            after = measure_accum_purge_blast_radius(con)
            if after.accum_observations != 0 or after.policy_snapshots != 0:
                con.rollback()
                raise RuntimeError("purge postcondition failed: accum rows remain after delete")
            if after.non_accum_observations != counts.non_accum_observations:
                con.rollback()
                raise RuntimeError(
                    "purge postcondition failed: non-accum observation count changed"
                )
            if after.preopen_labels != counts.preopen_labels:
                con.rollback()
                raise RuntimeError("purge postcondition failed: non-accum label count changed")
            con.commit()
            return AccumPurgeReport(
                db_path=str(path),
                counts=counts,
                executed=True,
                foreign_key_violations=0,
            )
        except Exception:
            con.rollback()
            raise
    finally:
        con.close()
