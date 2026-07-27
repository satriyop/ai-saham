"""
SQLite implementation of the RegimeObservationRepository port.

Schema: regime_observations — one row per (observation_date, semantic_compatibility_id).
Detection inputs are stored as a JSON fingerprint for deterministic replay.
Forward label columns start NULL and are filled retroactively via
update_forward_labels(); only NULL slots are written (idempotent fill).

Legacy rows migrated with semantic_compatibility_id = ''.

Layer: Infrastructure (Persistence)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from src.domain.value_objects.regime_detection_evidence import (
    RegimeDetectionEvidence,
    RegimeStability,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS regime_observations (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_date          TEXT NOT NULL,
    semantic_compatibility_id TEXT NOT NULL DEFAULT '',
    observation_contract      TEXT NOT NULL DEFAULT '',
    universe_name             TEXT NOT NULL DEFAULT '',
    benchmark_ticker          TEXT NOT NULL DEFAULT '',
    schema_version            INTEGER NOT NULL DEFAULT 1,
    regime                    TEXT NOT NULL,
    regime_score              REAL NOT NULL,
    regime_confidence         REAL NOT NULL,
    regime_stability          TEXT NOT NULL,
    days_in_regime            INTEGER,
    transition_warning        TEXT,
    detection_inputs_json     TEXT NOT NULL,
    forward_ihsg_return_5d    REAL,
    forward_ihsg_return_10d   REAL,
    forward_ihsg_return_20d   REAL,
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL,
    UNIQUE(observation_date, semantic_compatibility_id)
)
"""

_REBUILD_FROM_LEGACY = """
CREATE TABLE regime_observations_new (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_date          TEXT NOT NULL,
    semantic_compatibility_id TEXT NOT NULL DEFAULT '',
    observation_contract      TEXT NOT NULL DEFAULT '',
    universe_name             TEXT NOT NULL DEFAULT '',
    benchmark_ticker          TEXT NOT NULL DEFAULT '',
    schema_version            INTEGER NOT NULL DEFAULT 1,
    regime                    TEXT NOT NULL,
    regime_score              REAL NOT NULL,
    regime_confidence         REAL NOT NULL,
    regime_stability          TEXT NOT NULL,
    days_in_regime            INTEGER,
    transition_warning        TEXT,
    detection_inputs_json     TEXT NOT NULL,
    forward_ihsg_return_5d    REAL,
    forward_ihsg_return_10d   REAL,
    forward_ihsg_return_20d   REAL,
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL,
    UNIQUE(observation_date, semantic_compatibility_id)
);
INSERT INTO regime_observations_new
    (observation_date, semantic_compatibility_id, observation_contract,
     universe_name, benchmark_ticker, schema_version, regime, regime_score,
     regime_confidence, regime_stability, days_in_regime, transition_warning,
     detection_inputs_json, forward_ihsg_return_5d, forward_ihsg_return_10d,
     forward_ihsg_return_20d, created_at, updated_at)
SELECT
    observation_date, '', '', '', '',
    schema_version, regime, regime_score, regime_confidence, regime_stability,
    days_in_regime, transition_warning, detection_inputs_json,
    forward_ihsg_return_5d, forward_ihsg_return_10d, forward_ihsg_return_20d,
    created_at, updated_at
FROM regime_observations;
DROP TABLE regime_observations;
ALTER TABLE regime_observations_new RENAME TO regime_observations;
"""


class SQLiteRegimeObservationRepository:
    """Persists RegimeDetectionEvidence to SQLite, keyed by date + cohort."""

    def __init__(self, db_path: str | Path = "data.db") -> None:
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='regime_observations'"
            ).fetchone()
            if row is None:
                conn.execute(_CREATE_TABLE)
                conn.commit()
            elif "semantic_compatibility_id" not in (row[0] or ""):
                conn.executescript(_REBUILD_FROM_LEGACY)
                conn.commit()

        SqliteMigrationRunner(self._db_path).run(
            "regime_observations",
            [(0, "SELECT 1")],
        )

    # ── writes ────────────────────────────────────────────────────────────────

    def save(self, evidence: RegimeDetectionEvidence) -> None:
        """Upsert a regime observation for its date + cohort identity."""
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO regime_observations
                    (observation_date, semantic_compatibility_id, observation_contract,
                     universe_name, benchmark_ticker, schema_version, regime, regime_score,
                     regime_confidence, regime_stability, days_in_regime,
                     transition_warning, detection_inputs_json,
                     forward_ihsg_return_5d, forward_ihsg_return_10d,
                     forward_ihsg_return_20d, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_date, semantic_compatibility_id) DO UPDATE SET
                    observation_contract      = excluded.observation_contract,
                    universe_name             = excluded.universe_name,
                    benchmark_ticker          = excluded.benchmark_ticker,
                    schema_version            = excluded.schema_version,
                    regime                    = excluded.regime,
                    regime_score              = excluded.regime_score,
                    regime_confidence         = excluded.regime_confidence,
                    regime_stability          = excluded.regime_stability,
                    days_in_regime            = excluded.days_in_regime,
                    transition_warning        = excluded.transition_warning,
                    detection_inputs_json     = excluded.detection_inputs_json,
                    forward_ihsg_return_5d  = COALESCE(
                        regime_observations.forward_ihsg_return_5d,
                        excluded.forward_ihsg_return_5d
                    ),
                    forward_ihsg_return_10d = COALESCE(
                        regime_observations.forward_ihsg_return_10d,
                        excluded.forward_ihsg_return_10d
                    ),
                    forward_ihsg_return_20d = COALESCE(
                        regime_observations.forward_ihsg_return_20d,
                        excluded.forward_ihsg_return_20d
                    ),
                    updated_at                = excluded.updated_at
                """,
                (
                    evidence.observation_date.isoformat(),
                    evidence.semantic_compatibility_id,
                    evidence.observation_contract,
                    evidence.universe_name,
                    evidence.benchmark_ticker,
                    evidence.schema_version,
                    evidence.regime,
                    evidence.regime_score,
                    evidence.regime_confidence,
                    evidence.regime_stability.value,
                    evidence.days_in_regime,
                    evidence.transition_warning,
                    json.dumps(evidence.detection_inputs_dict()),
                    evidence.forward_ihsg_return_5d,
                    evidence.forward_ihsg_return_10d,
                    evidence.forward_ihsg_return_20d,
                    now,
                    now,
                ),
            )
            conn.commit()

    def update_forward_labels(
        self,
        observation_date: date,
        *,
        forward_ihsg_return_5d: float | None = None,
        forward_ihsg_return_10d: float | None = None,
        forward_ihsg_return_20d: float | None = None,
        semantic_compatibility_id: str = "",
    ) -> bool:
        """Fill forward label slots that are still NULL (idempotent) for one cohort."""
        updates: list[str] = []
        params: list = []

        if forward_ihsg_return_5d is not None:
            updates.append("forward_ihsg_return_5d = COALESCE(forward_ihsg_return_5d, ?)")
            params.append(forward_ihsg_return_5d)
        if forward_ihsg_return_10d is not None:
            updates.append("forward_ihsg_return_10d = COALESCE(forward_ihsg_return_10d, ?)")
            params.append(forward_ihsg_return_10d)
        if forward_ihsg_return_20d is not None:
            updates.append("forward_ihsg_return_20d = COALESCE(forward_ihsg_return_20d, ?)")
            params.append(forward_ihsg_return_20d)

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(observation_date.isoformat())
        params.append(semantic_compatibility_id)

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "UPDATE regime_observations SET "
                f"{', '.join(updates)} "
                "WHERE observation_date = ? AND semantic_compatibility_id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(
        self,
        observation_date: date,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> RegimeDetectionEvidence | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if semantic_compatibility_id is not None:
                row = conn.execute(
                    """
                    SELECT * FROM regime_observations
                    WHERE observation_date = ? AND semantic_compatibility_id = ?
                    """,
                    (observation_date.isoformat(), semantic_compatibility_id),
                ).fetchone()
                return _row_to_evidence(row) if row else None

            rows = conn.execute(
                "SELECT * FROM regime_observations WHERE observation_date = ?",
                (observation_date.isoformat(),),
            ).fetchall()
            if len(rows) == 1:
                return _row_to_evidence(rows[0])
            return None

    def get_recent(
        self,
        limit: int = 30,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> list[RegimeDetectionEvidence]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if semantic_compatibility_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM regime_observations
                    WHERE semantic_compatibility_id = ?
                    ORDER BY observation_date DESC
                    LIMIT ?
                    """,
                    (semantic_compatibility_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM regime_observations
                    ORDER BY observation_date DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [_row_to_evidence(r) for r in rows]


# ── serialization helpers ─────────────────────────────────────────────────────


def _row_to_evidence(row: sqlite3.Row) -> RegimeDetectionEvidence:
    inputs = json.loads(row["detection_inputs_json"])
    return RegimeDetectionEvidence(
        observation_date=date.fromisoformat(row["observation_date"]),
        schema_version=row["schema_version"],
        regime=row["regime"],
        regime_score=row["regime_score"],
        regime_confidence=row["regime_confidence"],
        regime_stability=RegimeStability(row["regime_stability"]),
        days_in_regime=row["days_in_regime"],
        transition_warning=row["transition_warning"],
        ihsg_20d_return=inputs.get("ihsg_20d_return"),
        ihsg_trend_structure=inputs.get("ihsg_trend_structure"),
        ihsg_breadth_pct_above_ma=inputs.get("ihsg_breadth_pct_above_ma"),
        ihsg_volume_trend=inputs.get("ihsg_volume_trend"),
        ihsg_atr_pct=inputs.get("ihsg_atr_pct"),
        idx_foreign_flow_5d=inputs.get("idx_foreign_flow_5d"),
        idx_foreign_flow_20d=inputs.get("idx_foreign_flow_20d"),
        foreign_buy_streak=inputs.get("foreign_buy_streak"),
        foreign_sell_streak=inputs.get("foreign_sell_streak"),
        banking_sector_vs_ihsg=inputs.get("banking_sector_vs_ihsg"),
        sector_breadth=inputs.get("sector_breadth"),
        forward_ihsg_return_5d=row["forward_ihsg_return_5d"],
        forward_ihsg_return_10d=row["forward_ihsg_return_10d"],
        forward_ihsg_return_20d=row["forward_ihsg_return_20d"],
        semantic_compatibility_id=row["semantic_compatibility_id"],
        observation_contract=row["observation_contract"],
        universe_name=row["universe_name"],
        benchmark_ticker=row["benchmark_ticker"],
    )
