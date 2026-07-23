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
from src.application.services.mce_observation_identity import build_mce_observation_identity
from src.infrastructure.config.market_context_config import default_market_context_config_path


DEFAULT_DB = Path("data/db/data.db")


@dataclass(frozen=True)
class PanelRow:
    ticker: str
    snapshot_date: str
    regime: str | None
    vwap_discount_pct: float | None
    bci_label: str | None
    total_net_value: float | None
    accum_score: float | None
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
    # Schema v8+: lean MATCH/PARTIAL/NO_MATCH per named setup (research/audit).
    # Empty dict when fingerprint omitted the field (should not happen on v8).
    named_setup_evaluations: dict[str, dict[str, Any]] | None = None
    # DecisionPolicy inputs (Package B6)
    signal_score: float | None = None
    entry_quality: str | None = None
    trade_setup_action: str | None = None
    signal_authority_coverage: float | None = None
    gate_tightening: bool | None = None
    decision_regime: str | None = None
    # RiskEngine inputs (Package C) — lean payload always; child table preferred
    risk_status: str | None = None
    risk_gate: str | None = None
    risk_confidence: int | None = None
    gate_is_structural: bool | None = None
    risk_source: str | None = None  # "child_table" | "payload" | None
    # BandarGate dig input (from candidate.bandar_detector)
    five_day_accdist: str | None = None


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


def _risk_fields_from_payload(payload_json: str) -> dict[str, Any]:
    """Lean risk summary from parent observation payload (always available on v8)."""
    cand = _candidate_fields(payload_json)
    trade_setup = json.loads(payload_json).get("trade_setup") or {}
    if not isinstance(trade_setup, dict):
        trade_setup = {}
    gate = cand.get("risk_gate")
    if gate is None:
        gate = trade_setup.get("gate_triggered")
    status = cand.get("risk_status")
    if status is None and trade_setup.get("action"):
        action = str(trade_setup.get("action")).upper()
        if action.startswith("BLOCKED"):
            status = "BLOCKED"
        elif action in {"ENTER", "WATCH", "AVOID"}:
            status = "OPEN"
    structural: bool | None = None
    action = _as_upper(trade_setup.get("action"))
    if action == "BLOCKED_STRUCTURAL":
        structural = True
    elif action == "BLOCKED_EXECUTION":
        structural = False
    return {
        "risk_status": _as_upper(status),
        "risk_gate": str(gate).strip() if gate else None,
        "risk_confidence": _as_int(cand.get("risk_confidence")),
        "gate_is_structural": structural,
        "risk_source": "payload" if status is not None or gate is not None else None,
    }


def _risk_fields_from_child(
    risk_assessment_json: str | None,
    gate_triggered: str | None,
    setup_action: str | None,
) -> dict[str, Any] | None:
    """Prefer authoritative child-table RiskAssessment when present."""
    if not risk_assessment_json:
        return None
    try:
        data = json.loads(risk_assessment_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    gate = data.get("gate_triggered")
    if gate is None:
        gate = gate_triggered
    status = "BLOCKED" if gate else "OPEN"
    structural = data.get("gate_is_structural")
    if structural is None and setup_action:
        action = str(setup_action).upper()
        if action == "BLOCKED_STRUCTURAL":
            structural = True
        elif action == "BLOCKED_EXECUTION":
            structural = False
    return {
        "risk_status": status,
        "risk_gate": str(gate).strip() if gate else None,
        "risk_confidence": _as_int(data.get("gate_confidence", data.get("confidence"))),
        "gate_is_structural": _as_bool(structural) if structural is not None else None,
        "risk_source": "child_table",
    }


def _observation_risk_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = 'observation_risk_assessments'
        """
    ).fetchone()
    return row is not None


def resolve_default_regime_cohort_id(
    *,
    universe_name: str = "lq45",
    benchmark_ticker: str = "IHSG",
) -> str:
    """Resolve current MCE cohort id from on-disk market_context_engine.yaml."""
    config_path = default_market_context_config_path()
    raw_yaml = config_path.read_text(encoding="utf-8")
    identity = build_mce_observation_identity(
        resolved_mce_config_canonical=raw_yaml,
        universe_name=universe_name,
        benchmark_ticker=benchmark_ticker,
    )
    return identity.cohort_id


def _regime_has_cohort_column(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='regime_observations'"
    ).fetchone()
    if row is None:
        return False
    return "semantic_compatibility_id" in (row[0] or "")


def _fetch_swing10d_rows(
    conn: sqlite3.Connection,
    *,
    cohort_id: str,
    has_risk_child: bool,
    regime_has_cohort: bool,
) -> list[sqlite3.Row]:
    risk_select = (
        """
                  ora.risk_assessment_json AS risk_assessment_json,
                  ora.gate_triggered AS child_gate_triggered,
                  ora.setup_action AS child_setup_action
        """
        if has_risk_child
        else """
                  NULL AS risk_assessment_json,
                  NULL AS child_gate_triggered,
                  NULL AS child_setup_action
        """
    )
    risk_join = (
        """
                LEFT JOIN observation_risk_assessments ora
                  ON c.ticker = ora.ticker
                 AND date(c.snapshot_date) = date(ora.snapshot_date)
                 AND c.workflow = ora.workflow
                 AND c.window_sessions = ora.window_sessions
                 AND date(c.data_as_of_date) = date(ora.data_as_of_date)
                 AND c.config_hash = ora.config_hash
        """
        if has_risk_child
        else ""
    )
    if regime_has_cohort:
        regime_join = """
                LEFT JOIN regime_observations r
                  ON date(c.snapshot_date) = date(r.observation_date)
                 AND r.semantic_compatibility_id = ?
        """
        params: tuple[object, ...] = (cohort_id, CANDIDATE_OBSERVATION_SCHEMA_VERSION)
    else:
        # Pre-cohort DB: date-only join (one regime row per day).
        regime_join = """
                LEFT JOIN regime_observations r
                  ON date(c.snapshot_date) = date(r.observation_date)
        """
        params = (CANDIDATE_OBSERVATION_SCHEMA_VERSION,)

    sql = f"""
            SELECT
              c.ticker,
              c.snapshot_date,
              c.payload_json,
              l.outcome_label,
              l.close_return,
              l.max_forward_return,
              l.max_adverse_excursion,
              r.regime,
              {risk_select}
            FROM candidate_observations c
            JOIN signal_forward_labels l
              ON c.ticker = l.ticker
             AND date(c.snapshot_date) = date(l.signal_date)
             AND c.captured_at = l.observation_captured_at
            {regime_join}
            {risk_join}
            WHERE l.horizon = 'SWING_10D'
              AND c.schema_version = ?
            ORDER BY c.snapshot_date, c.ticker
            """
    return conn.execute(sql, params).fetchall()


def load_swing10d_panel(
    db_path: Path | None = None,
    *,
    regime_cohort_id: str | None = None,
) -> list[PanelRow]:
    """Load canonical screen_accum panel joined to SWING_10D labels + regime.

    Regime rows are joined on ``semantic_compatibility_id`` when that column
    exists. By default the current MCE cohort is resolved from
    ``market_context_engine.yaml`` with universe ``lq45`` and benchmark
    ``IHSG``. Pass ``regime_cohort_id=""`` to join legacy tagged rows.
    Pre-cohort databases fall back to a date-only regime join.
    """
    path = resolve_db_path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    cohort_id = (
        resolve_default_regime_cohort_id()
        if regime_cohort_id is None
        else regime_cohort_id
    )

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = _fetch_swing10d_rows(
            conn,
            cohort_id=cohort_id,
            has_risk_child=_observation_risk_table_exists(conn),
            regime_has_cohort=_regime_has_cohort_column(conn),
        )
    finally:
        conn.close()

    panel: list[PanelRow] = []
    for row in rows:
        cand = _candidate_fields(row["payload_json"])
        decision = _decision_fields(row["payload_json"])
        named = _named_setup_evaluations(row["payload_json"])
        risk = _risk_fields_from_child(
            row["risk_assessment_json"],
            row["child_gate_triggered"],
            row["child_setup_action"],
        ) or _risk_fields_from_payload(row["payload_json"])
        breakdown = cand.get("accum_score_breakdown") or {}
        points = _component_points(breakdown)
        total = _as_float(cand.get("accum_score"))
        panel.append(
            PanelRow(
                ticker=row["ticker"],
                snapshot_date=str(row["snapshot_date"])[:10],
                regime=row["regime"],
                vwap_discount_pct=_as_float(cand.get("vwap_discount_pct")),
                bci_label=cand.get("bci_label"),
                total_net_value=_as_float(cand.get("total_net_value")),
                accum_score=total,
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
                named_setup_evaluations=named,
                signal_score=_as_float(decision.get("signal_score")),
                entry_quality=_as_upper(decision.get("entry_quality")),
                trade_setup_action=_as_upper(decision.get("trade_setup_action")),
                signal_authority_coverage=_as_float(
                    decision.get("signal_authority_coverage")
                ),
                gate_tightening=_as_bool(decision.get("gate_tightening")),
                decision_regime=_as_upper(decision.get("decision_regime")),
                risk_status=risk.get("risk_status"),
                risk_gate=risk.get("risk_gate"),
                risk_confidence=risk.get("risk_confidence"),
                gate_is_structural=risk.get("gate_is_structural"),
                risk_source=risk.get("risk_source"),
                five_day_accdist=_five_day_accdist(row["payload_json"]),
            )
        )
    return panel


def _five_day_accdist(payload_json: str) -> str | None:
    cand = _candidate_fields(payload_json)
    detector = cand.get("bandar_detector")
    if not isinstance(detector, dict):
        return None
    raw = detector.get("five_day_accdist")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _named_setup_evaluations(payload_json: str) -> dict[str, dict[str, Any]] | None:
    """Extract schema-v8 lean named setup evals from sub_signal_fingerprint."""
    payload = json.loads(payload_json)
    fingerprint = payload.get("sub_signal_fingerprint") or {}
    if not isinstance(fingerprint, dict):
        return None
    raw = fingerprint.get("named_setup_evaluations")
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, dict[str, Any]] = {}
    for setup_name, entry in raw.items():
        if isinstance(entry, dict):
            out[str(setup_name)] = entry
    return out or None


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
