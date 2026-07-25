"""
Generate open_30m outcome labels from saved pre-open observations + research pre-open track files.

Session-horizon twin of research signal labels (multi-day), scoped to pre-open:
does not extend SignalLabelHorizon (swing contracts stay untouched).

Labels are deterministic, offline, and join decisions saved at capture to
09:00–09:30 tracks without recomputing signal scores.

Layer: Application
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from src.application.use_case.opening_grade_use_case import (
    OPENING_DATA_DIR,
    _extract_observed_price,
)

OPEN_30M_LABEL_SCHEMA_VERSION = 1
OPEN_30M_HORIZON = "open_30m"


class _ObservationsReader(Protocol):
    def list_all_by_date(self, snapshot_date: date) -> list[Any]:
        ...


@dataclass(frozen=True)
class PreOpenOpen30mLabel:
    ticker: str
    signal_date: date
    horizon: str
    screen_result: str | None
    signal_score: int | None
    trade_setup_action: str | None
    entry_range_low: float | None
    entry_range_high: float | None
    opening_price: float | None
    entry_range_hit: bool | None
    peak_09_30: float | None
    trough_09_30: float | None
    close_proxy_09_30: float | None
    open_to_close_return_pct: float | None
    max_favorable_excursion_pct: float | None
    max_adverse_excursion_pct: float | None
    clean_trade: bool | None
    participated: bool | None  # open inside entry range when range known
    outcome: str  # SUCCESS | FAILURE | NEUTRAL | UNAVAILABLE
    unavailable_reason: str | None
    decision_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "signal_date": self.signal_date.isoformat(),
            "horizon": self.horizon,
            "screen_result": self.screen_result,
            "signal_score": self.signal_score,
            "trade_setup_action": self.trade_setup_action,
            "entry_range_low": self.entry_range_low,
            "entry_range_high": self.entry_range_high,
            "opening_price": self.opening_price,
            "entry_range_hit": self.entry_range_hit,
            "peak_09_30": self.peak_09_30,
            "trough_09_30": self.trough_09_30,
            "close_proxy_09_30": self.close_proxy_09_30,
            "open_to_close_return_pct": self.open_to_close_return_pct,
            "max_favorable_excursion_pct": self.max_favorable_excursion_pct,
            "max_adverse_excursion_pct": self.max_adverse_excursion_pct,
            "clean_trade": self.clean_trade,
            "participated": self.participated,
            "outcome": self.outcome,
            "unavailable_reason": self.unavailable_reason,
            "decision_source": self.decision_source,
        }


@dataclass(frozen=True)
class GeneratePreOpenOpen30mLabelsResult:
    labels: tuple[PreOpenOpen30mLabel, ...] = field(default_factory=tuple)
    decision_source: str = "none"
    observation_count: int = 0
    labeled_count: int = 0
    unavailable_count: int = 0
    output_path: str | None = None


def generate_pre_open_open30m_labels(
    run_date: date,
    *,
    observations_repository: _ObservationsReader | None = None,
    opening_data_dir: Path | None = None,
    persist: bool = True,
) -> GeneratePreOpenOpen30mLabelsResult:
    """Build open_30m labels for one session date; optionally write JSON artifact."""
    data_dir = opening_data_dir or OPENING_DATA_DIR
    day_dir = data_dir / run_date.strftime("%Y%m%d")

    track_files = sorted(day_dir.glob("track_*.json"))
    if not track_files:
        raise FileNotFoundError(
            f"No track files in {day_dir}. Run `saham research pre-open track` first."
        )
    tracks: list[dict] = []
    for tf in track_files:
        with open(tf) as f:
            tracks.append(json.load(f))

    decisions, decision_source = _load_decisions(
        run_date, observations_repository
    )
    if not decisions:
        raise FileNotFoundError(
            f"No saved pre-open observations for {run_date}. "
            "Run `saham research pre-open capture` first "
            "(day-file snapshot/export is not a decision source)."
        )

    labels: list[PreOpenOpen30mLabel] = []
    unavailable = 0
    for dec in decisions:
        label = _label_one(dec, tracks, run_date, decision_source)
        labels.append(label)
        if label.outcome == "UNAVAILABLE":
            unavailable += 1

    out_path: Path | None = None
    if persist:
        day_dir.mkdir(parents=True, exist_ok=True)
        out_path = day_dir / "open_30m_labels.json"
        artifact = {
            "schema_version": OPEN_30M_LABEL_SCHEMA_VERSION,
            "horizon": OPEN_30M_HORIZON,
            "date": run_date.isoformat(),
            "decision_source": decision_source,
            "observation_count": len(decisions),
            "labeled_count": len(labels) - unavailable,
            "unavailable_count": unavailable,
            "labels": [lb.to_dict() for lb in labels],
        }
        out_path.write_text(json.dumps(artifact, indent=2, default=str))

    return GeneratePreOpenOpen30mLabelsResult(
        labels=tuple(labels),
        decision_source=decision_source,
        observation_count=len(decisions),
        labeled_count=len(labels) - unavailable,
        unavailable_count=unavailable,
        output_path=str(out_path) if out_path else None,
    )


def _load_decisions(
    run_date: date,
    observations_repository: _ObservationsReader | None,
) -> tuple[list[dict], str]:
    """Load decisions from saved observations only (fail closed)."""
    from src.application.services.pre_open_observation_queries import (
        list_pre_open_observations_by_ticker,
    )

    by_ticker = list_pre_open_observations_by_ticker(
        observations_repository, run_date
    )
    if not by_ticker:
        return [], "none"
    return (
        [_decision_from_observation(r) for r in by_ticker.values()],
        "saved_observations",
    )


def _decision_from_observation(row: Any) -> dict:
    payload = getattr(row, "payload", None) or {}
    cand = payload.get("candidate") or {}
    signal = payload.get("signal") or {}
    trade = payload.get("trade_setup") or {}
    return {
        "ticker": row.ticker,
        "entry_range_low": _f(cand.get("entry_range_low")),
        "entry_range_high": _f(cand.get("entry_range_high")),
        "entry_price": _f(cand.get("entry_price")),
        "stop_loss_price": _f(cand.get("stop_loss_price")),
        "screen_result": payload.get("screen_result"),
        "signal_score": signal.get("score"),
        "trade_setup_action": trade.get("action"),
    }


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _label_one(
    dec: dict,
    tracks: list[dict],
    run_date: date,
    decision_source: str,
) -> PreOpenOpen30mLabel:
    ticker = dec["ticker"]
    price_series: list[float] = []
    for track in tracks:
        observed = _extract_observed_price(track.get("tickers", {}).get(ticker))
        if observed is not None:
            price_series.append(observed[0])

    if not price_series:
        return PreOpenOpen30mLabel(
            ticker=ticker,
            signal_date=run_date,
            horizon=OPEN_30M_HORIZON,
            screen_result=dec.get("screen_result"),
            signal_score=dec.get("signal_score"),
            trade_setup_action=dec.get("trade_setup_action"),
            entry_range_low=dec.get("entry_range_low"),
            entry_range_high=dec.get("entry_range_high"),
            opening_price=None,
            entry_range_hit=None,
            peak_09_30=None,
            trough_09_30=None,
            close_proxy_09_30=None,
            open_to_close_return_pct=None,
            max_favorable_excursion_pct=None,
            max_adverse_excursion_pct=None,
            clean_trade=None,
            participated=None,
            outcome="UNAVAILABLE",
            unavailable_reason="no_track_prices",
            decision_source=decision_source,
        )

    opening = price_series[0]
    peak = max(price_series)
    trough = min(price_series)
    close_proxy = price_series[-1]
    lo, hi = dec.get("entry_range_low"), dec.get("entry_range_high")
    entry_range_hit = (
        lo is not None and hi is not None and lo <= opening <= hi
    )
    participated = entry_range_hit if lo is not None and hi is not None else None

    open_to_close = round((close_proxy - opening) / opening * 100, 4)
    mfe = round((peak - opening) / opening * 100, 4)
    mae = round((trough - opening) / opening * 100, 4)

    stop = dec.get("stop_loss_price")
    entry = dec.get("entry_price")
    one_r = None
    if entry is not None and stop is not None and entry > stop:
        one_r = entry - stop
    clean_trade = None
    if one_r and opening:
        clean_trade = (peak >= opening + one_r) and (trough > opening - one_r)

    # Outcome policy (session): participate + positive open→close without stop
    if participated is False:
        outcome = "NEUTRAL"
        reason = "open_outside_entry_range"
    elif open_to_close is not None and open_to_close > 0.15:
        outcome = "SUCCESS"
        reason = None
    elif open_to_close is not None and open_to_close < -0.15:
        outcome = "FAILURE"
        reason = None
    else:
        outcome = "NEUTRAL"
        reason = None

    return PreOpenOpen30mLabel(
        ticker=ticker,
        signal_date=run_date,
        horizon=OPEN_30M_HORIZON,
        screen_result=dec.get("screen_result"),
        signal_score=dec.get("signal_score"),
        trade_setup_action=dec.get("trade_setup_action"),
        entry_range_low=lo,
        entry_range_high=hi,
        opening_price=opening,
        entry_range_hit=entry_range_hit,
        peak_09_30=round(peak, 2),
        trough_09_30=round(trough, 2),
        close_proxy_09_30=round(close_proxy, 2),
        open_to_close_return_pct=open_to_close,
        max_favorable_excursion_pct=mfe,
        max_adverse_excursion_pct=mae,
        clean_trade=clean_trade,
        participated=participated,
        outcome=outcome,
        unavailable_reason=reason,
        decision_source=decision_source,
    )
