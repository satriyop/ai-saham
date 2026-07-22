"""Read-only research panel from canonical observations + labels.

Layer: research lab (outside hexagonal product layers).
Authority: none.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data/db/data.db")


@dataclass(frozen=True)
class PanelRow:
    ticker: str
    snapshot_date: str
    regime: str | None
    vwap_discount_pct: float | None
    bci_label: str | None
    total_net_value: float | None
    foreign_flow_score: float | None
    outcome_label: str
    close_return: float | None
    max_forward_return: float | None
    max_adverse_excursion: float | None


def resolve_db_path(db_path: Path | None = None) -> Path:
    path = (db_path or DEFAULT_DB).expanduser()
    if not path.is_absolute():
        # Prefer CWD; fall back to repo root relative to this file.
        cwd_candidate = Path.cwd() / path
        if cwd_candidate.exists():
            return cwd_candidate
        repo_root = Path(__file__).resolve().parents[2]
        return repo_root / path
    return path


def _candidate_fields(payload_json: str) -> dict[str, Any]:
    payload = json.loads(payload_json)
    candidate = payload.get("candidate") or {}
    if not isinstance(candidate, dict):
        return {}
    return candidate


def load_swing10d_panel(db_path: Path | None = None) -> list[PanelRow]:
    """Load canonical screen_accum panel joined to SWING_10D labels + regime."""
    path = resolve_db_path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              c.ticker,
              c.snapshot_date,
              c.payload_json,
              l.outcome_label,
              l.close_return,
              l.max_forward_return,
              l.max_adverse_excursion,
              r.regime
            FROM candidate_observations c
            JOIN signal_forward_labels l
              ON c.ticker = l.ticker
             AND date(c.snapshot_date) = date(l.signal_date)
             AND c.captured_at = l.observation_captured_at
            LEFT JOIN regime_observations r
              ON date(c.snapshot_date) = date(r.observation_date)
            WHERE l.horizon = 'SWING_10D'
            ORDER BY c.snapshot_date, c.ticker
            """
        ).fetchall()
    finally:
        conn.close()

    panel: list[PanelRow] = []
    for row in rows:
        cand = _candidate_fields(row["payload_json"])
        panel.append(
            PanelRow(
                ticker=row["ticker"],
                snapshot_date=str(row["snapshot_date"])[:10],
                regime=row["regime"],
                vwap_discount_pct=_as_float(cand.get("vwap_discount_pct")),
                bci_label=cand.get("bci_label"),
                total_net_value=_as_float(cand.get("total_net_value")),
                foreign_flow_score=_as_float(cand.get("foreign_flow_score")),
                outcome_label=row["outcome_label"],
                close_return=_as_float(row["close_return"]),
                max_forward_return=_as_float(row["max_forward_return"]),
                max_adverse_excursion=_as_float(row["max_adverse_excursion"]),
            )
        )
    return panel


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
