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

from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)


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
    # Accum feeder raw inputs + component points (Package A1)
    net_buy_ratio: float | None = None
    consecutive_streak: int | None = None
    avg_flow_ratio: float | None = None
    rsi: float | None = None
    points_cons: float | None = None
    points_streak: float | None = None
    points_vwap: float | None = None
    points_rsi: float | None = None
    points_flow: float | None = None
    points_inst: float | None = None
    score_without_cons: float | None = None
    score_without_streak: float | None = None
    score_without_vwap: float | None = None
    score_without_rsi: float | None = None
    score_without_flow: float | None = None
    score_without_inst: float | None = None
    sector_breadth_pct: float | None = None
    sector_breadth_bonus: float | None = None
    # Broker-list inputs (Package A4)
    window_days: int | None = None
    bci_tier1_count: int | None = None
    institutional_flag: bool | None = None
    top_brokers: tuple[str, ...] | None = None
    # Setup-gate inputs (Package B2)
    trend: str | None = None
    bb_width_pctile: float | None = None
    # DecisionPolicy inputs (Package B6)
    signal_score: float | None = None
    entry_quality: str | None = None
    trade_setup_action: str | None = None
    signal_authority_coverage: float | None = None
    gate_tightening: bool | None = None
    decision_regime: str | None = None


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


def _decision_fields(payload_json: str) -> dict[str, Any]:
    payload = json.loads(payload_json)
    signal = payload.get("signal") or {}
    assessment = signal.get("assessment") if isinstance(signal, dict) else {}
    if not isinstance(assessment, dict):
        assessment = {}
    constraints = assessment.get("decision_constraints") or {}
    if not isinstance(constraints, dict):
        constraints = {}
    trade_setup = payload.get("trade_setup") or {}
    if not isinstance(trade_setup, dict):
        trade_setup = {}
    coverage = assessment.get("signal_authority_coverage")
    if coverage is None and isinstance(signal, dict):
        coverage = signal.get("signal_authority_coverage")
    return {
        "signal_score": assessment.get("score", trade_setup.get("signal_score")),
        "entry_quality": assessment.get("entry_quality"),
        "trade_setup_action": trade_setup.get("action"),
        "signal_authority_coverage": coverage,
        "gate_tightening": trade_setup.get("gate_tightening"),
        "decision_regime": constraints.get("regime"),
    }


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
              AND c.schema_version = ?
            ORDER BY c.snapshot_date, c.ticker
            """,
            (CANDIDATE_OBSERVATION_SCHEMA_VERSION,),
        ).fetchall()
    finally:
        conn.close()

    panel: list[PanelRow] = []
    for row in rows:
        cand = _candidate_fields(row["payload_json"])
        decision = _decision_fields(row["payload_json"])
        breakdown = cand.get("foreign_flow_score_breakdown") or {}
        points = _component_points(breakdown)
        total = _as_float(cand.get("foreign_flow_score"))
        panel.append(
            PanelRow(
                ticker=row["ticker"],
                snapshot_date=str(row["snapshot_date"])[:10],
                regime=row["regime"],
                vwap_discount_pct=_as_float(cand.get("vwap_discount_pct")),
                bci_label=cand.get("bci_label"),
                total_net_value=_as_float(cand.get("total_net_value")),
                foreign_flow_score=total,
                outcome_label=row["outcome_label"],
                close_return=_as_float(row["close_return"]),
                max_forward_return=_as_float(row["max_forward_return"]),
                max_adverse_excursion=_as_float(row["max_adverse_excursion"]),
                net_buy_ratio=_as_float(cand.get("net_buy_ratio")),
                consecutive_streak=_as_int(cand.get("consecutive_streak")),
                avg_flow_ratio=_as_float(cand.get("avg_flow_ratio")),
                rsi=_as_float(cand.get("rsi")),
                points_cons=points.get("cons"),
                points_streak=points.get("streak"),
                points_vwap=points.get("vwap"),
                points_rsi=points.get("rsi"),
                points_flow=points.get("flow"),
                points_inst=points.get("inst"),
                score_without_cons=_without(total, points.get("cons")),
                score_without_streak=_without(total, points.get("streak")),
                score_without_vwap=_without(total, points.get("vwap")),
                score_without_rsi=_without(total, points.get("rsi")),
                score_without_flow=_without(total, points.get("flow")),
                score_without_inst=_without(total, points.get("inst")),
                sector_breadth_pct=_as_float(cand.get("sector_breadth_pct")),
                sector_breadth_bonus=_as_float(cand.get("sector_breadth_bonus")),
                window_days=_as_int(cand.get("window_days")),
                bci_tier1_count=_as_int(cand.get("bci_tier1_count")),
                institutional_flag=_as_bool(cand.get("institutional_flag")),
                top_brokers=_as_broker_codes(cand.get("top_brokers")),
                trend=_as_trend(cand.get("trend")),
                bb_width_pctile=_as_float(cand.get("bb_width_pctile")),
                signal_score=_as_float(decision.get("signal_score")),
                entry_quality=_as_upper(decision.get("entry_quality")),
                trade_setup_action=_as_upper(decision.get("trade_setup_action")),
                signal_authority_coverage=_as_float(
                    decision.get("signal_authority_coverage")
                ),
                gate_tightening=_as_bool(decision.get("gate_tightening")),
                decision_regime=_as_upper(decision.get("decision_regime")),
            )
        )
    return panel


def _component_points(breakdown: dict[str, Any]) -> dict[str, float | None]:
    raw = breakdown.get("breakdown") if isinstance(breakdown, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {k: _as_float(raw.get(k)) for k in ("cons", "streak", "vwap", "rsi", "flow", "inst")}


def _without(total: float | None, points: float | None) -> float | None:
    if total is None or points is None:
        return None
    return total - points


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _as_broker_codes(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    codes = tuple(str(code).strip().upper() for code in value if str(code).strip())
    return codes if codes else tuple()


def _as_trend(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _as_upper(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None
