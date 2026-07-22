"""Read-only Market Context / regime panel for research cards.

Layer: research lab (outside hexagonal product layers).
Authority: none.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.lab.panel import resolve_db_path


@dataclass(frozen=True)
class MceFactorPoint:
    name: str
    enabled: bool
    score: float | None
    weight: float | None
    label: str | None
    value: float | None


@dataclass(frozen=True)
class MceDayRow:
    as_of_date: str
    regime: str
    conviction: float
    gate_tightening: bool
    signal_multiplier: float
    regime_confidence: float | None
    regime_stability: str | None
    forward_ihsg_return_5d: float | None
    forward_ihsg_return_10d: float | None
    forward_ihsg_return_20d: float | None
    factors: tuple[MceFactorPoint, ...]


def load_mce_regime_panel(db_path: Path | None = None) -> list[MceDayRow]:
    """Join market_context_snapshots to regime_observations forward IHSG labels."""
    path = resolve_db_path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              m.as_of_date,
              m.regime,
              m.conviction,
              m.gate_tightening,
              m.signal_multiplier,
              m.regime_confidence,
              m.regime_stability,
              m.factors_json,
              r.forward_ihsg_return_5d,
              r.forward_ihsg_return_10d,
              r.forward_ihsg_return_20d
            FROM market_context_snapshots m
            LEFT JOIN regime_observations r
              ON date(m.as_of_date) = date(r.observation_date)
            ORDER BY m.as_of_date
            """
        ).fetchall()
    finally:
        conn.close()

    panel: list[MceDayRow] = []
    for row in rows:
        factors = _parse_factors(row["factors_json"])
        panel.append(
            MceDayRow(
                as_of_date=str(row["as_of_date"])[:10],
                regime=row["regime"],
                conviction=float(row["conviction"]),
                gate_tightening=bool(row["gate_tightening"]),
                signal_multiplier=float(row["signal_multiplier"]),
                regime_confidence=_as_float(row["regime_confidence"]),
                regime_stability=row["regime_stability"],
                forward_ihsg_return_5d=_as_float(row["forward_ihsg_return_5d"]),
                forward_ihsg_return_10d=_as_float(row["forward_ihsg_return_10d"]),
                forward_ihsg_return_20d=_as_float(row["forward_ihsg_return_20d"]),
                factors=factors,
            )
        )
    return panel


def _parse_factors(factors_json: str) -> tuple[MceFactorPoint, ...]:
    raw = json.loads(factors_json)
    if not isinstance(raw, list):
        return ()
    out: list[MceFactorPoint] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            MceFactorPoint(
                name=str(item.get("name") or "unknown"),
                enabled=bool(item.get("enabled", False)),
                score=_as_float(item.get("score")),
                weight=_as_float(item.get("weight")),
                label=item.get("label"),
                value=_as_float(item.get("value")),
            )
        )
    return tuple(out)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
