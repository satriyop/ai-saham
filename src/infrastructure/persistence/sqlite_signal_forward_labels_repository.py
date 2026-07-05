"""SQLite repository for deterministic signal forward labels."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS signal_forward_labels (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                   TEXT    NOT NULL,
    signal_date              TEXT    NOT NULL,
    horizon                  TEXT    NOT NULL,
    observation_captured_at  TEXT    NOT NULL DEFAULT '',
    entry_reference_price    TEXT,
    label_window_start       TEXT,
    label_window_end         TEXT,
    close_return             REAL,
    max_forward_return       REAL,
    max_adverse_excursion    REAL,
    days_to_peak             INTEGER,
    days_to_trough           INTEGER,
    stop_would_trigger       INTEGER,
    target_would_trigger     INTEGER,
    outcome_label            TEXT    NOT NULL,
    unavailable_reason       TEXT,
    fingerprint_json         TEXT    NOT NULL,
    schema_version           INTEGER NOT NULL DEFAULT 1,
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    UNIQUE(ticker, signal_date, horizon, observation_captured_at)
)
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_signal_forward_labels_ticker_date
ON signal_forward_labels(ticker, signal_date, horizon)
"""


class SQLiteSignalForwardLabelsRepository:
    """Persists schema-versioned signal_forward_labels records."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        runner = SqliteMigrationRunner(self._db_path)
        runner.run(
            "signal_forward_labels",
            [
                (0, _CREATE_TABLE),
                (1, _CREATE_INDEX),
            ],
        )

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_many(self, labels: list[SignalForwardLabel]) -> None:
        if not labels:
            return
        now = datetime.now(UTC).isoformat()
        rows = []
        for label in labels:
            rows.append(
                (
                    label.ticker.upper(),
                    label.signal_date.isoformat(),
                    label.horizon.value,
                    (
                        label.observation_captured_at.isoformat()
                        if label.observation_captured_at
                        else ""
                    ),
                    (
                        str(label.entry_reference_price)
                        if label.entry_reference_price is not None
                        else None
                    ),
                    (label.label_window_start.isoformat() if label.label_window_start else None),
                    label.label_window_end.isoformat() if label.label_window_end else None,
                    label.close_return,
                    label.max_forward_return,
                    label.max_adverse_excursion,
                    label.days_to_peak,
                    label.days_to_trough,
                    _bool_to_db(label.stop_would_trigger),
                    _bool_to_db(label.target_would_trigger),
                    label.outcome_label.value,
                    label.unavailable_reason,
                    json.dumps(
                        label.fingerprint.to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    label.schema_version,
                    now,
                    now,
                )
            )
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO signal_forward_labels
                    (ticker, signal_date, horizon, observation_captured_at,
                     entry_reference_price, label_window_start, label_window_end,
                     close_return, max_forward_return, max_adverse_excursion,
                     days_to_peak, days_to_trough, stop_would_trigger,
                     target_would_trigger, outcome_label, unavailable_reason,
                     fingerprint_json, schema_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, signal_date, horizon, observation_captured_at)
                DO UPDATE SET
                    entry_reference_price = excluded.entry_reference_price,
                    label_window_start = excluded.label_window_start,
                    label_window_end = excluded.label_window_end,
                    close_return = excluded.close_return,
                    max_forward_return = excluded.max_forward_return,
                    max_adverse_excursion = excluded.max_adverse_excursion,
                    days_to_peak = excluded.days_to_peak,
                    days_to_trough = excluded.days_to_trough,
                    stop_would_trigger = excluded.stop_would_trigger,
                    target_would_trigger = excluded.target_would_trigger,
                    outcome_label = excluded.outcome_label,
                    unavailable_reason = excluded.unavailable_reason,
                    fingerprint_json = excluded.fingerprint_json,
                    schema_version = excluded.schema_version,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def get(
        self,
        ticker: str,
        signal_date: date,
        horizon: SignalLabelHorizon,
    ) -> SignalForwardLabel | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM signal_forward_labels
                WHERE ticker = ? AND signal_date = ? AND horizon = ?
                ORDER BY observation_captured_at DESC, id DESC
                LIMIT 1
                """,
                (ticker.upper(), signal_date.isoformat(), horizon.value),
            ).fetchone()
        return _row_to_label(row) if row else None

    def get_at(
        self,
        ticker: str,
        signal_date: date,
        horizon: SignalLabelHorizon,
        observation_captured_at: datetime,
    ) -> SignalForwardLabel | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM signal_forward_labels
                WHERE ticker = ?
                  AND signal_date = ?
                  AND horizon = ?
                  AND observation_captured_at = ?
                LIMIT 1
                """,
                (
                    ticker.upper(),
                    signal_date.isoformat(),
                    horizon.value,
                    observation_captured_at.isoformat(),
                ),
            ).fetchone()
        return _row_to_label(row) if row else None

    def list(
        self,
        *,
        signal_date: date | None = None,
        horizon: SignalLabelHorizon | None = None,
        ticker: str | None = None,
    ) -> list[SignalForwardLabel]:
        clauses: list[str] = []
        params: list[str] = []
        if signal_date is not None:
            clauses.append("signal_date = ?")
            params.append(signal_date.isoformat())
        if horizon is not None:
            clauses.append("horizon = ?")
            params.append(horizon.value)
        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM signal_forward_labels
                {where}
                ORDER BY signal_date DESC, ticker ASC, horizon ASC, observation_captured_at DESC
                """,
                params,
            ).fetchall()
        return [_row_to_label(row) for row in rows]


def _row_to_label(row: sqlite3.Row) -> SignalForwardLabel:
    schema_version = int(row["schema_version"])
    if schema_version > 1:
        raise ValueError(f"Unsupported signal forward label schema_version={schema_version}")
    return SignalForwardLabel(
        ticker=row["ticker"],
        signal_date=date.fromisoformat(row["signal_date"]),
        horizon=SignalLabelHorizon(row["horizon"]),
        entry_reference_price=(
            None
            if row["entry_reference_price"] is None
            else Decimal(str(row["entry_reference_price"]))
        ),
        label_window_start=_date_or_none(row["label_window_start"]),
        label_window_end=_date_or_none(row["label_window_end"]),
        close_return=row["close_return"],
        max_forward_return=row["max_forward_return"],
        max_adverse_excursion=row["max_adverse_excursion"],
        days_to_peak=row["days_to_peak"],
        days_to_trough=row["days_to_trough"],
        stop_would_trigger=_bool_from_db(row["stop_would_trigger"]),
        target_would_trigger=_bool_from_db(row["target_would_trigger"]),
        outcome_label=SignalForwardOutcome(row["outcome_label"]),
        unavailable_reason=row["unavailable_reason"],
        fingerprint=SignalObservationFingerprint.from_dict(json.loads(row["fingerprint_json"])),
        observation_captured_at=(
            datetime.fromisoformat(row["observation_captured_at"])
            if row["observation_captured_at"]
            else None
        ),
        schema_version=schema_version,
    )


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _bool_to_db(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _bool_from_db(value: int | None) -> bool | None:
    if value is None:
        return None
    return bool(value)
