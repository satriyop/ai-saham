"""SQLite repository for observation-linked risk assessment detail rows.

Ownership rules mirror ``observation_risk_assessment_repository`` port docstring.
Child rows share canonical identity with parent ``candidate_observations`` and
are written only alongside a parent upsert — never standalone by cron.

Layer: Infrastructure
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from src.domain.ports.observation_risk_assessment_repository import (
    ObservationRiskAssessmentRecord,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

OBSERVATION_RISK_ASSESSMENT_SCHEMA_VERSION = 1

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS observation_risk_assessments (
  ticker TEXT NOT NULL,
  snapshot_date TEXT NOT NULL,
  workflow TEXT NOT NULL,
  window_sessions INTEGER NOT NULL,
  data_as_of_date TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  assessed_at TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1,
  risk_assessment_json TEXT NOT NULL,
  trade_setup_json TEXT,
  gate_triggered TEXT,
  setup_action TEXT,
  PRIMARY KEY (ticker, snapshot_date, workflow, window_sessions, data_as_of_date, config_hash)
)
"""

_IDENTITY_CONFLICT_TARGET = (
    "(ticker, snapshot_date, workflow, window_sessions, data_as_of_date, config_hash)"
)

_UPSERT_SQL = f"""
INSERT INTO observation_risk_assessments (
    ticker, snapshot_date, workflow, window_sessions, data_as_of_date, config_hash,
    assessed_at, schema_version, risk_assessment_json, trade_setup_json,
    gate_triggered, setup_action
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT {_IDENTITY_CONFLICT_TARGET}
DO UPDATE SET
    assessed_at = excluded.assessed_at,
    schema_version = excluded.schema_version,
    risk_assessment_json = excluded.risk_assessment_json,
    trade_setup_json = excluded.trade_setup_json,
    gate_triggered = excluded.gate_triggered,
    setup_action = excluded.setup_action
"""


def ensure_observation_risk_assessments_schema(db_path: str | Path) -> None:
    runner = SqliteMigrationRunner(Path(db_path).expanduser())
    runner.run(
        "observation_risk_assessments",
        [(0, _CREATE_TABLE)],
    )


def _records_to_rows(
    records: list[ObservationRiskAssessmentRecord],
) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for record in records:
        rows.append(
            (
                record.ticker.upper(),
                record.snapshot_date.isoformat(),
                record.workflow,
                record.window_sessions,
                record.data_as_of_date.isoformat(),
                record.config_hash,
                record.assessed_at.isoformat(),
                record.schema_version,
                json.dumps(
                    record.risk_assessment_json,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                (
                    json.dumps(
                        record.trade_setup_json,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if record.trade_setup_json is not None
                    else None
                ),
                record.gate_triggered,
                record.setup_action,
            )
        )
    return rows


def write_observation_risk_assessments(
    conn: sqlite3.Connection,
    records: list[ObservationRiskAssessmentRecord],
) -> int:
    if not records:
        return 0
    conn.executemany(_UPSERT_SQL, _records_to_rows(records))
    return len(records)


class SQLiteObservationRiskAssessmentRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        ensure_observation_risk_assessments_schema(self._db_path)

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_many(self, records: list[ObservationRiskAssessmentRecord]) -> int:
        if not records:
            return 0
        with self._connect() as conn:
            return write_observation_risk_assessments(conn, records)

    def get_by_identity(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        workflow: str,
        window_sessions: int,
        data_as_of_date: date,
        config_hash: str,
    ) -> ObservationRiskAssessmentRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    ticker, snapshot_date, workflow, window_sessions, data_as_of_date,
                    config_hash, assessed_at, schema_version, risk_assessment_json,
                    trade_setup_json, gate_triggered, setup_action
                FROM observation_risk_assessments
                WHERE ticker = ?
                  AND snapshot_date = ?
                  AND workflow = ?
                  AND window_sessions = ?
                  AND data_as_of_date = ?
                  AND config_hash = ?
                """,
                (
                    ticker.upper(),
                    snapshot_date.isoformat(),
                    workflow,
                    window_sessions,
                    data_as_of_date.isoformat(),
                    config_hash,
                ),
            ).fetchone()
        if row is None:
            return None
        trade_setup_json = (
            json.loads(row["trade_setup_json"]) if row["trade_setup_json"] else None
        )
        return ObservationRiskAssessmentRecord(
            ticker=row["ticker"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            workflow=row["workflow"],
            window_sessions=row["window_sessions"],
            data_as_of_date=date.fromisoformat(row["data_as_of_date"]),
            config_hash=row["config_hash"],
            assessed_at=datetime.fromisoformat(row["assessed_at"]),
            schema_version=row["schema_version"],
            risk_assessment_json=json.loads(row["risk_assessment_json"]),
            trade_setup_json=trade_setup_json,
            gate_triggered=row["gate_triggered"],
            setup_action=row["setup_action"],
        )
