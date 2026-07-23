"""
SQLite implementation of the MarketContextRepository port.

Schema: market_context_snapshots — one row per (as_of_date, semantic_compatibility_id).
Factors are stored as a JSON array to avoid a separate table; this snapshot is
read-only after write (no mutations), so denormalization is acceptable.

Legacy rows migrated with semantic_compatibility_id = ''.

Layer: Infrastructure (Persistence)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from src.domain.value_objects.market_context import (
    ContextFactor,
    MarketContext,
    MarketRegime,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS market_context_snapshots (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of_date                TEXT NOT NULL,
    semantic_compatibility_id TEXT NOT NULL DEFAULT '',
    observation_contract      TEXT NOT NULL DEFAULT '',
    universe_name             TEXT NOT NULL DEFAULT '',
    benchmark_ticker          TEXT NOT NULL DEFAULT '',
    regime                    TEXT NOT NULL,
    conviction                REAL NOT NULL,
    signal_multiplier         REAL NOT NULL,
    gate_tightening           INTEGER NOT NULL,
    factors_json              TEXT NOT NULL,
    staleness_warning         TEXT,
    coverage_warning          TEXT,
    created_at                TEXT NOT NULL,
    regime_confidence         REAL,
    regime_stability          TEXT,
    days_in_regime            INTEGER,
    transition_warning        TEXT,
    UNIQUE(as_of_date, semantic_compatibility_id)
)
"""

_REBUILD_FROM_LEGACY = """
CREATE TABLE market_context_snapshots_new (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of_date                TEXT NOT NULL,
    semantic_compatibility_id TEXT NOT NULL DEFAULT '',
    observation_contract      TEXT NOT NULL DEFAULT '',
    universe_name             TEXT NOT NULL DEFAULT '',
    benchmark_ticker          TEXT NOT NULL DEFAULT '',
    regime                    TEXT NOT NULL,
    conviction                REAL NOT NULL,
    signal_multiplier         REAL NOT NULL,
    gate_tightening           INTEGER NOT NULL,
    factors_json              TEXT NOT NULL,
    staleness_warning         TEXT,
    coverage_warning          TEXT,
    created_at                TEXT NOT NULL,
    regime_confidence         REAL,
    regime_stability          TEXT,
    days_in_regime            INTEGER,
    transition_warning        TEXT,
    UNIQUE(as_of_date, semantic_compatibility_id)
);
INSERT INTO market_context_snapshots_new
    (as_of_date, semantic_compatibility_id, observation_contract,
     universe_name, benchmark_ticker, regime, conviction, signal_multiplier,
     gate_tightening, factors_json, staleness_warning, coverage_warning,
     created_at, regime_confidence, regime_stability, days_in_regime,
     transition_warning)
SELECT
    as_of_date, '', '', '', '',
    regime, conviction, signal_multiplier, gate_tightening, factors_json,
    staleness_warning, coverage_warning, created_at, regime_confidence,
    regime_stability, days_in_regime, transition_warning
FROM market_context_snapshots;
DROP TABLE market_context_snapshots;
ALTER TABLE market_context_snapshots_new RENAME TO market_context_snapshots;
"""


class SQLiteMarketContextRepository:
    """Persists MarketContext snapshots to SQLite, keyed by date + cohort."""

    def __init__(self, db_path: str | Path = "data.db") -> None:
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='market_context_snapshots'"
            ).fetchone()
            if row is None:
                conn.execute(_CREATE_TABLE)
                conn.commit()
            elif "semantic_compatibility_id" not in (row[0] or ""):
                conn.executescript(_REBUILD_FROM_LEGACY)
                conn.commit()

        SqliteMigrationRunner(self._db_path).run(
            "market_context_snapshots",
            [(0, "SELECT 1")],
        )

    # ── writes ────────────────────────────────────────────────────────────────

    def save(
        self,
        context: MarketContext,
        *,
        semantic_compatibility_id: str = "",
        observation_contract: str = "",
        universe_name: str = "",
        benchmark_ticker: str = "",
    ) -> None:
        """Upsert a snapshot for its date + cohort identity."""
        factors_json = json.dumps([_factor_to_dict(f) for f in context.factors])
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO market_context_snapshots
                    (as_of_date, semantic_compatibility_id, observation_contract,
                     universe_name, benchmark_ticker, regime, conviction,
                     signal_multiplier, gate_tightening, factors_json,
                     staleness_warning, coverage_warning,
                     regime_confidence, regime_stability, days_in_regime,
                     transition_warning, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(as_of_date, semantic_compatibility_id) DO UPDATE SET
                    observation_contract = excluded.observation_contract,
                    universe_name        = excluded.universe_name,
                    benchmark_ticker     = excluded.benchmark_ticker,
                    regime               = excluded.regime,
                    conviction           = excluded.conviction,
                    signal_multiplier    = excluded.signal_multiplier,
                    gate_tightening      = excluded.gate_tightening,
                    factors_json         = excluded.factors_json,
                    staleness_warning    = excluded.staleness_warning,
                    coverage_warning     = excluded.coverage_warning,
                    regime_confidence    = excluded.regime_confidence,
                    regime_stability     = excluded.regime_stability,
                    days_in_regime       = excluded.days_in_regime,
                    transition_warning   = excluded.transition_warning,
                    created_at           = excluded.created_at
                """,
                (
                    context.as_of_date.isoformat(),
                    semantic_compatibility_id,
                    observation_contract,
                    universe_name,
                    benchmark_ticker,
                    context.regime.value,
                    context.conviction,
                    context.signal_multiplier,
                    int(context.gate_tightening),
                    factors_json,
                    context.staleness_warning,
                    context.coverage_warning,
                    getattr(context, "regime_confidence", None),
                    getattr(context, "regime_stability", None),
                    getattr(context, "days_in_regime", None),
                    getattr(context, "transition_warning", None),
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(
        self,
        as_of_date: date,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> MarketContext | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if semantic_compatibility_id is not None:
                row = conn.execute(
                    """
                    SELECT * FROM market_context_snapshots
                    WHERE as_of_date = ? AND semantic_compatibility_id = ?
                    """,
                    (as_of_date.isoformat(), semantic_compatibility_id),
                ).fetchone()
                return _row_to_context(row) if row else None

            rows = conn.execute(
                "SELECT * FROM market_context_snapshots WHERE as_of_date = ?",
                (as_of_date.isoformat(),),
            ).fetchall()
            if len(rows) == 1:
                return _row_to_context(rows[0])
            return None

    def get_recent(
        self,
        limit: int = 30,
        *,
        semantic_compatibility_id: str | None = None,
    ) -> list[MarketContext]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if semantic_compatibility_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM market_context_snapshots
                    WHERE semantic_compatibility_id = ?
                    ORDER BY as_of_date DESC
                    LIMIT ?
                    """,
                    (semantic_compatibility_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM market_context_snapshots
                    ORDER BY as_of_date DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [_row_to_context(r) for r in rows]


# ── serialization helpers ─────────────────────────────────────────────────────

def _factor_to_dict(f: ContextFactor) -> dict:
    return {
        "name": f.name,
        "enabled": f.enabled,
        "value": f.value,
        "score": f.score,
        "weight": f.weight,
        "label": f.label,
        "rationale": f.rationale,
    }


def _dict_to_factor(d: dict) -> ContextFactor:
    return ContextFactor(
        name=d["name"],
        enabled=d["enabled"],
        value=d.get("value"),
        score=d.get("score"),
        weight=d["weight"],
        label=d["label"],
        rationale=d["rationale"],
    )


def _row_to_context(row: sqlite3.Row) -> MarketContext:
    factors = tuple(_dict_to_factor(d) for d in json.loads(row["factors_json"]))
    row_dict = dict(row)
    return MarketContext(
        regime=MarketRegime(row["regime"]),
        conviction=row["conviction"],
        factors=factors,
        signal_multiplier=row["signal_multiplier"],
        gate_tightening=bool(row["gate_tightening"]),
        as_of_date=date.fromisoformat(row["as_of_date"]),
        staleness_warning=row["staleness_warning"],
        coverage_warning=row["coverage_warning"],
        regime_confidence=row_dict.get("regime_confidence"),
        regime_stability=row_dict.get("regime_stability"),
        days_in_regime=row_dict.get("days_in_regime"),
        transition_warning=row_dict.get("transition_warning"),
    )
