"""
SQLite implementation of the RegimeObservationRepository port.

Schema: regime_observations — one row per observation_date (upsert on conflict).
Detection inputs are stored as a JSON fingerprint for deterministic replay.
Forward label columns start NULL and are filled retroactively via
update_forward_labels(); only NULL slots are written (idempotent fill).

schema_version = 1 for all A2 observations.

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

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS regime_observations (
    observation_date          TEXT NOT NULL PRIMARY KEY,
    schema_version            INTEGER NOT NULL DEFAULT 1,
    -- Regime output
    regime                    TEXT NOT NULL,
    regime_score              REAL NOT NULL,
    regime_confidence         REAL NOT NULL,
    regime_stability          TEXT NOT NULL,
    days_in_regime            INTEGER,
    transition_warning        TEXT,
    -- Detection inputs fingerprint (all raw IHSG/flow values)
    detection_inputs_json     TEXT NOT NULL,
    -- Forward labels (initially NULL; filled retroactively when future candles available)
    forward_ihsg_return_5d    REAL,
    forward_ihsg_return_10d   REAL,
    forward_ihsg_return_20d   REAL,
    -- Metadata
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL
)
"""


class SQLiteRegimeObservationRepository:
    """Persists RegimeDetectionEvidence to SQLite, one record per observation_date."""

    def __init__(self, db_path: str | Path = "data.db") -> None:
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_CREATE_TABLE)
            conn.commit()

    # ── writes ────────────────────────────────────────────────────────────────

    def save(self, evidence: RegimeDetectionEvidence) -> None:
        """Upsert a regime observation.

        On conflict: non-label fields are replaced with the new values (re-evaluation
        may produce a slightly different score if config changes), while forward label
        columns are preserved via COALESCE so that retroactively filled labels are
        never erased by a re-evaluation of the same date.
        """
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO regime_observations
                    (observation_date, schema_version, regime, regime_score,
                     regime_confidence, regime_stability, days_in_regime,
                     transition_warning, detection_inputs_json,
                     forward_ihsg_return_5d, forward_ihsg_return_10d,
                     forward_ihsg_return_20d, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_date) DO UPDATE SET
                    schema_version        = excluded.schema_version,
                    regime                = excluded.regime,
                    regime_score          = excluded.regime_score,
                    regime_confidence     = excluded.regime_confidence,
                    regime_stability      = excluded.regime_stability,
                    days_in_regime        = excluded.days_in_regime,
                    transition_warning    = excluded.transition_warning,
                    detection_inputs_json = excluded.detection_inputs_json,
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
                    updated_at            = excluded.updated_at
                """,
                (
                    evidence.observation_date.isoformat(),
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
    ) -> bool:
        """Fill forward label slots that are still NULL (idempotent).

        Returns True if the observation existed and at least one label was written.
        """
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

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                f"UPDATE regime_observations SET {', '.join(updates)} WHERE observation_date = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, observation_date: date) -> RegimeDetectionEvidence | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM regime_observations WHERE observation_date = ?",
                (observation_date.isoformat(),),
            ).fetchone()
        return _row_to_evidence(row) if row else None

    def get_recent(self, limit: int = 30) -> list[RegimeDetectionEvidence]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM regime_observations ORDER BY observation_date DESC LIMIT ?",
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
    )
