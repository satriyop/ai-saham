"""Write same-day ops packaging from a pre-open capture response.

Ops day files are **not** decision authority. Learning truth is only
``candidate_observations`` written by research pre-open capture (ADR-048).

The export supports:
- learn track ticker discovery when DB is unavailable offline is not required
  (track loads tickers from DB); this file feeds today briefing + learn prompt.
- human-readable session journal under data/opening/YYYYMMDD/

Layer: Application
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.domain.value_objects.idx_market import IDX_TIMEZONE

if TYPE_CHECKING:
    from src.application.use_case.pre_open_workflow_use_case import (
        PreOpenWorkflowRequest,
        PreOpenWorkflowResponse,
    )

OPS_SESSION_FILENAME = "ops_session.json"


def write_pre_open_ops_day_export(
    response: "PreOpenWorkflowResponse",
    request: "PreOpenWorkflowRequest",
    day_dir: Path,
    *,
    captured_at: datetime | None = None,
    recorded_count: int = 0,
) -> Path:
    """Persist non-authority ops session export for the capture run.

    Returns path to ops_session.json.
    """
    now = captured_at or datetime.now(tz=IDX_TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IDX_TIMEZONE)

    run_date = response.result.screened_date
    candidates_out: list[dict[str, Any]] = []
    for c in response.result.candidates:
        ticker = c.ticker
        entry = float(c.entry_price) if c.entry_price is not None else None
        stop = float(c.stop_loss_price) if c.stop_loss_price is not None else None
        one_r = round(entry - stop, 2) if entry is not None and stop is not None else None
        sig = (
            response.signal_by_ticker.get(ticker)
            if response.signal_by_ticker is not None
            else None
        )
        trade = (
            response.trade_setup_by_ticker.get(ticker)
            if response.trade_setup_by_ticker is not None
            else None
        )
        risk = (
            response.risk_by_ticker.get(ticker)
            if response.risk_by_ticker is not None
            else None
        )
        candidates_out.append(
            {
                "ticker": ticker,
                "iev": c.iev,
                "iep": getattr(c, "iep", None),
                "entry_range_low": (
                    float(c.entry_range_low) if c.entry_range_low is not None else None
                ),
                "entry_range_high": (
                    float(c.entry_range_high) if c.entry_range_high is not None else None
                ),
                "suggested_entry": entry,
                "atr_stop": stop,
                "one_r": one_r,
                "trend": c.trend_signal,
                "rsi": round(float(c.rsi), 2) if c.rsi is not None else None,
                "atr": round(float(c.atr), 2) if c.atr is not None else None,
                "opening_broker_backing_tag": c.opening_broker_backing_tag,
                "opening_broker_backing_score": (
                    round(c.opening_broker_backing_score, 1)
                    if c.opening_broker_backing_score is not None
                    else None
                ),
                "iev_intensity": (
                    round(c.iev_intensity, 3) if c.iev_intensity is not None else None
                ),
                "unusual_volume": c.unusual_volume,
                "bid_pressure_preopen": c.bid_offer_imbalance,
                "ticker_notation": (
                    c.ticker_notation.to_dict() if c.ticker_notation else None
                ),
                "signal_score": getattr(sig, "score", None) if sig else None,
                "signal_strength": getattr(sig, "strength", None) if sig else None,
                "signal_entry_quality": (
                    getattr(sig, "entry_quality", None) if sig else None
                ),
                "trade_setup_action": (
                    trade.action.value if trade is not None and hasattr(trade.action, "value")
                    else (str(trade.action) if trade is not None else None)
                ),
                "risk_level_name": (
                    getattr(risk, "risk_level_name", None) if risk else None
                ),
            }
        )

    phase = request.capture_phase if request.capture_phase != "UNKNOWN" else "NCP_LOCKED"
    payload = {
        "schema_version": 1,
        "artifact_type": "pre_open_ops_export",
        "decision_authority": "candidate_observations",
        "workflow": "screen_pre_open",
        "observation_contract": "pre-open-open-30m",
        "recorded_count": recorded_count,
        "captured_at": now.isoformat(),
        "date": str(run_date),
        "capture_phase": phase,
        "capture_valid_for_opening_prediction": phase in ("PRE_NCP", "NCP_LOCKED"),
        "capture_confidence": (
            "HIGH" if phase == "NCP_LOCKED" else ("MEDIUM" if phase == "PRE_NCP" else "LOW")
        ),
        "is_ncp_locked": phase == "NCP_LOCKED",
        "source_status": response.source_status.value,
        "candidates": candidates_out,
        "warnings": list(response.warnings or ()),
    }

    day_dir.mkdir(parents=True, exist_ok=True)
    out_path = day_dir / OPS_SESSION_FILENAME
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return out_path
