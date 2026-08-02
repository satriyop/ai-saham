"""SQLite setup phase ledger — production memory for sequence validation.

Layer: Infrastructure
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Sequence

from src.domain.ports.setup_phase_history_repository import (
    GENERIC_SETUP_FAMILY,
    SCHEMA_VERSION_V1,
    SetupPhaseLedgerRow,
    SetupPhaseRecordResult,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

MIGRATION_NAMESPACE = "setup_phase_ledger"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS setup_phase_ledger (
    entry_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    phase TEXT NOT NULL,
    setup_family TEXT NOT NULL DEFAULT '',
    source_workflow TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    observation_id TEXT,
    UNIQUE (ticker, as_of_date, setup_family, source_workflow)
)
"""

_CREATE_INDEX_TICKER_DATE = """
CREATE INDEX IF NOT EXISTS idx_setup_phase_ledger_ticker_date
ON setup_phase_ledger (ticker, as_of_date)
"""

_CREATE_INDEX_TICKER_FAMILY_DATE = """
CREATE INDEX IF NOT EXISTS idx_setup_phase_ledger_ticker_family_date
ON setup_phase_ledger (ticker, setup_family, as_of_date)
"""

_MIGRATIONS: list[tuple[int, str]] = [
    (0, _CREATE_TABLE),
    (1, _CREATE_INDEX_TICKER_DATE),
    (2, _CREATE_INDEX_TICKER_FAMILY_DATE),
]


def _normalize_family(setup_family: str | None) -> str:
    if not setup_family:
        return GENERIC_SETUP_FAMILY
    return str(setup_family).strip().lower().replace("_", "-")


def _entry_id(
    *,
    ticker: str,
    as_of_date: date,
    setup_family: str,
    source_workflow: str,
) -> str:
    raw = f"{ticker.upper()}|{as_of_date.isoformat()}|{setup_family}|{source_workflow}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _row_from_db(row: sqlite3.Row) -> SetupPhaseLedgerRow:
    return SetupPhaseLedgerRow(
        entry_id=str(row["entry_id"]),
        ticker=str(row["ticker"]).upper(),
        as_of_date=date.fromisoformat(str(row["as_of_date"])),
        phase=SetupPhaseState(str(row["phase"])),
        setup_family=str(row["setup_family"] or GENERIC_SETUP_FAMILY),
        source_workflow=str(row["source_workflow"]),
        recorded_at=str(row["recorded_at"]),
        schema_version=int(row["schema_version"]),
        observation_id=(str(row["observation_id"]) if row["observation_id"] is not None else None),
    )


class SQLiteSetupPhaseLedgerRepository:
    """Indexed closed-session phase facts for setup sequence validation."""

    def __init__(self, db_path: str | Path = "data.db") -> None:
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        SqliteMigrationRunner(self._db_path).run(MIGRATION_NAMESPACE, _MIGRATIONS)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def list_rows_before(
        self,
        *,
        ticker: str,
        before_date: date,
        limit: int | None = None,
    ) -> Sequence[SetupPhaseLedgerRow]:
        sql = """
            SELECT entry_id, ticker, as_of_date, phase, setup_family,
                   source_workflow, recorded_at, schema_version, observation_id
            FROM setup_phase_ledger
            WHERE ticker = ? AND as_of_date < ?
            ORDER BY as_of_date ASC, entry_id ASC
        """
        params: list[object] = [ticker.upper(), before_date.isoformat()]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return tuple(_row_from_db(r) for r in rows)

    def list_rows_before_many(
        self,
        *,
        tickers: Sequence[str],
        before_date: date,
    ) -> Sequence[SetupPhaseLedgerRow]:
        normalized = sorted({str(t).upper() for t in tickers if t})
        if not normalized:
            return ()
        placeholders = ",".join("?" for _ in normalized)
        sql = f"""
            SELECT entry_id, ticker, as_of_date, phase, setup_family,
                   source_workflow, recorded_at, schema_version, observation_id
            FROM setup_phase_ledger
            WHERE ticker IN ({placeholders}) AND as_of_date < ?
            ORDER BY ticker ASC, as_of_date ASC, entry_id ASC
        """
        params: list[object] = [*normalized, before_date.isoformat()]
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return tuple(_row_from_db(r) for r in rows)

    def record_phase(
        self,
        *,
        ticker: str,
        as_of_date: date,
        phase: SetupPhaseState,
        setup_family: str | None,
        source_workflow: str,
        observation_id: str | None = None,
    ) -> SetupPhaseRecordResult:
        if phase is SetupPhaseState.NONE:
            return SetupPhaseRecordResult.SKIPPED_POLICY

        family = _normalize_family(setup_family)
        ticker_u = ticker.upper()
        workflow = str(source_workflow).strip() or "screen_accum"
        entry_id = _entry_id(
            ticker=ticker_u,
            as_of_date=as_of_date,
            setup_family=family,
            source_workflow=workflow,
        )
        recorded_at = datetime.now(UTC).isoformat()

        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT phase FROM setup_phase_ledger
                WHERE ticker = ? AND as_of_date = ? AND setup_family = ?
                  AND source_workflow = ?
                """,
                (ticker_u, as_of_date.isoformat(), family, workflow),
            ).fetchone()
            if existing is not None:
                if str(existing["phase"]) == phase.value:
                    return SetupPhaseRecordResult.SKIPPED_IDENTICAL
                conn.execute(
                    """
                    UPDATE setup_phase_ledger
                    SET phase = ?, recorded_at = ?, schema_version = ?,
                        observation_id = COALESCE(?, observation_id),
                        entry_id = ?
                    WHERE ticker = ? AND as_of_date = ? AND setup_family = ?
                      AND source_workflow = ?
                    """,
                    (
                        phase.value,
                        recorded_at,
                        SCHEMA_VERSION_V1,
                        observation_id,
                        entry_id,
                        ticker_u,
                        as_of_date.isoformat(),
                        family,
                        workflow,
                    ),
                )
                return SetupPhaseRecordResult.UPDATED

            conn.execute(
                """
                INSERT INTO setup_phase_ledger (
                    entry_id, ticker, as_of_date, phase, setup_family,
                    source_workflow, recorded_at, schema_version, observation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    ticker_u,
                    as_of_date.isoformat(),
                    phase.value,
                    family,
                    workflow,
                    recorded_at,
                    SCHEMA_VERSION_V1,
                    observation_id,
                ),
            )
            return SetupPhaseRecordResult.INSERTED


class SQLiteSetupPhaseLedgerReadRepository:
    """Fail-closed read-only setup-phase history over an existing database."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        if not self._db_path.is_file():
            raise FileNotFoundError(
                f"setup phase database does not exist (read-only): {self._db_path}"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def list_rows_before(
        self,
        *,
        ticker: str,
        before_date: date,
        limit: int | None = None,
    ) -> Sequence[SetupPhaseLedgerRow]:
        sql = """
            SELECT entry_id, ticker, as_of_date, phase, setup_family,
                   source_workflow, recorded_at, schema_version, observation_id
            FROM setup_phase_ledger
            WHERE ticker = ? AND as_of_date < ?
            ORDER BY as_of_date ASC, entry_id ASC
        """
        params: list[object] = [ticker.upper(), before_date.isoformat()]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        try:
            with self._connect() as connection:
                rows = connection.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return ()
            raise
        return tuple(_row_from_db(row) for row in rows)

    def list_rows_before_many(
        self,
        *,
        tickers: Sequence[str],
        before_date: date,
    ) -> Sequence[SetupPhaseLedgerRow]:
        normalized = sorted({str(ticker).upper() for ticker in tickers if ticker})
        if not normalized:
            return ()
        placeholders = ",".join("?" for _ in normalized)
        sql = f"""
            SELECT entry_id, ticker, as_of_date, phase, setup_family,
                   source_workflow, recorded_at, schema_version, observation_id
            FROM setup_phase_ledger
            WHERE ticker IN ({placeholders}) AND as_of_date < ?
            ORDER BY ticker ASC, as_of_date ASC, entry_id ASC
        """
        params: list[object] = [*normalized, before_date.isoformat()]
        try:
            with self._connect() as connection:
                rows = connection.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return ()
            raise
        return tuple(_row_from_db(row) for row in rows)

    def record_phase(
        self,
        *,
        ticker: str,
        as_of_date: date,
        phase: SetupPhaseState,
        setup_family: str | None,
        source_workflow: str,
        observation_id: str | None = None,
    ) -> SetupPhaseRecordResult:
        del ticker, as_of_date, phase, setup_family, source_workflow, observation_id
        raise PermissionError("setup phase ledger is read-only")
