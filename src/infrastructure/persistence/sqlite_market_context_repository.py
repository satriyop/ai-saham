"""
SQLite implementation of the MarketContextRepository port.

Schema: market_context_snapshots — one row per as_of_date (upsert on conflict).
Factors are stored as a JSON array to avoid a separate table; this snapshot is
read-only after write (no mutations), so denormalization is acceptable.

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

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS market_context_snapshots (
    as_of_date        TEXT NOT NULL PRIMARY KEY,
    regime            TEXT NOT NULL,
    conviction        REAL NOT NULL,
    signal_multiplier REAL NOT NULL,
    gate_tightening   INTEGER NOT NULL,
    factors_json      TEXT NOT NULL,
    staleness_warning TEXT,
    coverage_warning  TEXT,
    created_at        TEXT NOT NULL
)
"""


class SQLiteMarketContextRepository:
    """Persists MarketContext snapshots to SQLite, one record per date."""

    def __init__(self, db_path: str | Path = "data.db") -> None:
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_CREATE_TABLE)
            conn.commit()

    # ── writes ────────────────────────────────────────────────────────────────

    def save(self, context: MarketContext) -> None:
        """Upsert: replaces any existing snapshot for the same date."""
        factors_json = json.dumps([_factor_to_dict(f) for f in context.factors])
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO market_context_snapshots
                    (as_of_date, regime, conviction, signal_multiplier, gate_tightening,
                     factors_json, staleness_warning, coverage_warning, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context.as_of_date.isoformat(),
                    context.regime.value,
                    context.conviction,
                    context.signal_multiplier,
                    int(context.gate_tightening),
                    factors_json,
                    context.staleness_warning,
                    context.coverage_warning,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, as_of_date: date) -> MarketContext | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM market_context_snapshots WHERE as_of_date = ?",
                (as_of_date.isoformat(),),
            ).fetchone()
        return _row_to_context(row) if row else None

    def get_recent(self, limit: int = 30) -> list[MarketContext]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM market_context_snapshots ORDER BY as_of_date DESC LIMIT ?",
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
    return MarketContext(
        regime=MarketRegime(row["regime"]),
        conviction=row["conviction"],
        factors=factors,
        signal_multiplier=row["signal_multiplier"],
        gate_tightening=bool(row["gate_tightening"]),
        as_of_date=date.fromisoformat(row["as_of_date"]),
        staleness_warning=row["staleness_warning"],
        coverage_warning=row["coverage_warning"],
    )
