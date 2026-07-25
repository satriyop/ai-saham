"""
opening_grade — deterministic accuracy analysis for the opening session learning loop.

Joins NCP decisions with track_*.json prices and computes session metrics.

Decision authority (clean break):
  Saved DB observations only (workflow=screen_pre_open).
  No snapshot.json / ops export as decision source.

Does not recompute signal scores; uses decisions saved at capture time.
Keeps grade.json / grade.md for learn tune/prompt.

Layer: Application
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from src.application.services.pre_open_observation_queries import (
    list_pre_open_observations_by_ticker,
)
from src.application.services.pre_open_ops_day_export import OPS_SESSION_FILENAME

OPENING_DATA_DIR = Path("data/opening")
GRADE_SCHEMA_VERSION = 2  # Phase 4: saved observations + signal/TradeSetup slices


class _ObservationsReader(Protocol):
    def list_all_by_date(self, snapshot_date: date) -> list[Any]:
        ...


def compute_grade(
    run_date: date | None = None,
    config_snapshot: dict | None = None,
    *,
    observations_repository: _ObservationsReader | None = None,
) -> dict:
    """
    Load tracks + decisions and compute accuracy report.
    Saves grade.json and grade.md. Returns the grade dict.
    """
    today = run_date or date.today()
    day_dir = OPENING_DATA_DIR / today.strftime("%Y%m%d")

    track_files = sorted(day_dir.glob("track_*.json"))
    if not track_files:
        raise FileNotFoundError(
            f"No track files found in {day_dir}. Run `saham learn track` first."
        )

    tracks: list[dict] = []
    for tf in track_files:
        with open(tf) as f:
            tracks.append(json.load(f))

    # Optional ops packaging for session meta only (not decision authority)
    ops_meta: dict = {}
    ops_path = day_dir / OPS_SESSION_FILENAME
    if ops_path.exists():
        try:
            with open(ops_path) as f:
                ops_meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            ops_meta = {}

    decision_source, candidates = _load_decision_candidates(
        today,
        observations_repository=observations_repository,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No saved pre-open observations for {today}. "
            "Run `saham research pre-open capture` first "
            "(day-file snapshot/export is not a decision source)."
        )

    per_ticker: list[dict] = []
    for cand in candidates:
        per_ticker.append(_grade_one_ticker(cand, tracks, ops_meta=ops_meta))

    tracked = [t for t in per_ticker if not t.get("no_track_data")]
    grade = _build_session_grade(
        today=today,
        ops_meta=ops_meta,
        decision_source=decision_source,
        candidates=candidates,
        per_ticker=per_ticker,
        tracked=tracked,
        config_snapshot=config_snapshot or {},
    )

    day_dir.mkdir(parents=True, exist_ok=True)
    with open(day_dir / "grade.json", "w") as f:
        json.dump(grade, f, indent=2, default=str)
    _write_grade_md(grade, day_dir / "grade.md")
    return grade


def _load_decision_candidates(
    today: date,
    *,
    observations_repository: _ObservationsReader | None,
) -> tuple[str, list[dict]]:
    """Return (source_label, normalized candidate decision dicts). Fail closed."""
    by_ticker = list_pre_open_observations_by_ticker(observations_repository, today)
    if not by_ticker:
        return "none", []
    normalized = [_candidate_from_observation(row) for row in by_ticker.values()]
    return "saved_observations", normalized


def _candidate_from_observation(row: Any) -> dict:
    payload = getattr(row, "payload", None) or {}
    cand = payload.get("candidate") or {}
    signal = payload.get("signal") or {}
    risk = payload.get("risk") or {}
    trade_setup = payload.get("trade_setup") or {}

    entry_low = _num(cand.get("entry_range_low"))
    entry_high = _num(cand.get("entry_range_high"))
    stop = _num(cand.get("stop_loss_price"))
    entry = _num(cand.get("entry_price"))
    one_r = None
    if entry is not None and stop is not None and entry > stop:
        one_r = entry - stop

    return {
        "ticker": row.ticker,
        "opening_setup": cand.get("opening_setup"),  # usually absent; legacy only
        "trend": cand.get("trend_signal") or cand.get("trend"),
        "iep": _num(cand.get("iep")),
        "entry_range_low": entry_low,
        "entry_range_high": entry_high,
        "one_r": one_r,
        "bid_pressure_preopen": cand.get("bid_offer_imbalance"),
        "screen_result": payload.get("screen_result"),
        "signal_score": signal.get("score"),
        "signal_strength": signal.get("strength"),
        "signal_entry_quality": signal.get("entry_quality"),
        "trade_setup_action": trade_setup.get("action"),
        "risk_level_name": risk.get("risk_level_name"),
        "decision_source": "saved_observations",
        "capture_phase": payload.get("capture_phase"),
    }


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _grade_one_ticker(cand: dict, tracks: list[dict], *, ops_meta: dict) -> dict:
    ticker = cand["ticker"]
    one_r = cand.get("one_r")
    entry_low = cand.get("entry_range_low")
    entry_high = cand.get("entry_range_high")
    trend = cand.get("trend")
    iep = cand.get("iep")
    opening_setup = cand.get("opening_setup") or "SKIP"
    bid_pressure_preopen = cand.get("bid_pressure_preopen")

    price_series: list[tuple[str, float, str, str]] = []
    for track in tracks:
        tdata = track.get("tickers", {}).get(ticker)
        observed = _extract_observed_price(tdata)
        if observed is not None:
            price, source, confidence = observed
            price_series.append((track["captured_at"], price, source, confidence))

    base_meta = {
        "ticker": ticker,
        "opening_setup": opening_setup,
        "trend": trend,
        "screen_result": cand.get("screen_result"),
        "signal_score": cand.get("signal_score"),
        "signal_strength": cand.get("signal_strength"),
        "signal_entry_quality": cand.get("signal_entry_quality"),
        "trade_setup_action": cand.get("trade_setup_action"),
        "risk_level_name": cand.get("risk_level_name"),
        "decision_source": cand.get("decision_source"),
        "signal_band": _signal_band(cand.get("signal_score")),
    }

    if not price_series:
        return {**base_meta, "no_track_data": True}

    opening_price = price_series[0][1]
    opening_price_source = price_series[0][2]
    opening_price_confidence = price_series[0][3]
    prices = [p for _, p, _, _ in price_series]
    peak = max(prices)
    trough = min(prices)

    entry_range_hit = (
        entry_low is not None
        and entry_high is not None
        and entry_low <= opening_price <= entry_high
    )

    iep_error_pct = (
        round(abs(iep - opening_price) / opening_price * 100, 3)
        if iep and opening_price
        else None
    )

    def price_at(n_snapshots: int) -> float | None:
        return price_series[n_snapshots][1] if len(price_series) > n_snapshots else None

    trend_bullish = trend == "BULLISH"

    def trend_correct(p: float | None) -> bool | None:
        if p is None:
            return None
        return (p > opening_price) == trend_bullish

    trend_T5 = trend_correct(price_at(1))
    trend_T15 = trend_correct(price_at(3))
    trend_T30 = trend_correct(price_at(6))

    one_r_available = None
    stop_hit = None
    clean_trade = None
    if opening_price and one_r:
        target = opening_price + one_r
        effective_stop = opening_price - one_r
        one_r_available = peak >= target
        stop_hit = trough <= effective_stop
        clean_trade = one_r_available and not stop_hit

    broker_signals: list[dict] = []
    for track in tracks:
        tdata = track.get("tickers", {}).get(ticker)
        if isinstance(tdata, dict) and isinstance(tdata.get("broker_signal"), dict):
            broker_signals.append(tdata["broker_signal"])

    institutional_absorption_rate = None
    broker_dominant_side = None
    if broker_signals:
        absorptions = [
            s["absorption_ratio"]
            for s in broker_signals
            if s.get("absorption_ratio") is not None
        ]
        institutional_absorption_rate = (
            round(sum(absorptions) / len(absorptions), 4) if absorptions else None
        )
        sides = [s["dominant_side"] for s in broker_signals if s.get("dominant_side")]
        if sides:
            broker_dominant_side = max(set(sides), key=sides.count)

    ob_series: list[dict] = []
    for track in tracks:
        tdata = track.get("tickers", {}).get(ticker)
        if isinstance(tdata, dict) and isinstance(tdata.get("order_book"), dict):
            ob_series.append(tdata["order_book"])

    bid_pressure_T0 = ob_series[0].get("bid_pressure_ratio") if ob_series else None
    bid_pressure_T5 = ob_series[1].get("bid_pressure_ratio") if len(ob_series) > 1 else None
    bid_momentum = (
        round(bid_pressure_T5 - bid_pressure_T0, 4)
        if bid_pressure_T0 is not None and bid_pressure_T5 is not None
        else None
    )
    fnet_T0 = ob_series[0].get("fnet_intraday") if ob_series else None
    fnet_latest = ob_series[-1].get("fnet_intraday") if ob_series else None

    capture_phase = cand.get("capture_phase") or ops_meta.get("capture_phase")

    return {
        **base_meta,
        "iep": iep,
        "opening_price": opening_price,
        "opening_price_source": opening_price_source,
        "opening_price_confidence": opening_price_confidence,
        "capture_phase": capture_phase,
        "peak_09_30": round(peak, 2),
        "trough_09_30": round(trough, 2),
        "entry_range_hit": entry_range_hit,
        "iep_error_pct": iep_error_pct,
        "trend_T5": trend_T5,
        "trend_T15": trend_T15,
        "trend_T30": trend_T30,
        "one_r_available": one_r_available,
        "stop_hit": stop_hit,
        "clean_trade": clean_trade,
        "bid_pressure_preopen": bid_pressure_preopen,
        "bid_pressure_T0": bid_pressure_T0,
        "bid_pressure_T5": bid_pressure_T5,
        "bid_momentum": bid_momentum,
        "fnet_T0": fnet_T0,
        "fnet_latest": fnet_latest,
        "institutional_absorption_rate": institutional_absorption_rate,
        "broker_dominant_side": broker_dominant_side,
        "price_series": [
            {
                "captured_at": captured_at,
                "price": price,
                "source": source,
                "confidence": confidence,
            }
            for captured_at, price, source, confidence in price_series
        ],
    }


def _signal_band(score: Any) -> str | None:
    if score is None:
        return None
    try:
        s = int(score)
    except (TypeError, ValueError):
        return None
    if s >= 70:
        return "strong"
    if s >= 50:
        return "moderate"
    return "weak"


def _build_session_grade(
    *,
    today: date,
    ops_meta: dict,
    decision_source: str,
    candidates: list[dict],
    per_ticker: list[dict],
    tracked: list[dict],
    config_snapshot: dict,
) -> dict:
    def rate(items: list[dict], key: str):
        vals = [t[key] for t in items if t.get(key) is not None]
        return round(sum(1 for v in vals if v) / len(vals), 3) if vals else None

    def slice_stats(subset: list[dict]) -> dict:
        if not subset:
            return {"count": 0}
        return {
            "count": len(subset),
            "entry_range_hit_rate": rate(subset, "entry_range_hit"),
            "clean_trade_rate": rate(subset, "clean_trade"),
            "trend_accuracy_T5": rate(subset, "trend_T5"),
            "trend_accuracy_T30": rate(subset, "trend_T30"),
        }

    def by_key(key: str, values: tuple[str, ...]) -> dict:
        out: dict[str, dict] = {}
        for v in values:
            subset = [
                t
                for t in per_ticker
                if t.get(key) == v and not t.get("no_track_data")
            ]
            out[v] = slice_stats(subset)
        # unknown / missing bucket
        known = set(values)
        other = [
            t
            for t in per_ticker
            if not t.get("no_track_data")
            and t.get(key) not in known
            and t.get(key) is not None
        ]
        if other:
            out["_other"] = slice_stats(other)
        missing = [
            t
            for t in per_ticker
            if not t.get("no_track_data") and t.get(key) is None
        ]
        if missing:
            out["_missing"] = slice_stats(missing)
        return out

    iep_errors = [t["iep_error_pct"] for t in tracked if t.get("iep_error_pct") is not None]
    session_meta = {
        "capture_phase": ops_meta.get("capture_phase")
        or (candidates[0].get("capture_phase") if candidates else None),
        "capture_valid_for_opening_prediction": ops_meta.get(
            "capture_valid_for_opening_prediction"
        ),
        "capture_confidence": ops_meta.get("capture_confidence"),
        "is_ncp_locked": ops_meta.get("is_ncp_locked"),
    }
    data_quality = _compute_data_quality(session_meta, tracked)
    data_quality["decision_source"] = decision_source

    # Champion slices (ADR-048 Phase 4)
    by_signal_band = by_key("signal_band", ("strong", "moderate", "weak"))
    by_screen_result = by_key(
        "screen_result",
        (
            "pass",
            "rejected_plan",
            "rejected_auction_missing",
            "rejected_signal",
            "rejected_risk",
        ),
    )
    by_trade_setup_action = by_key(
        "trade_setup_action",
        (
            "ENTER",
            "WATCH",
            "AVOID",
            "BLOCKED_EXECUTION",
            "BLOCKED_STRUCTURAL",
        ),
    )

    # Legacy secondary strata (not champion KPI)
    by_opening_setup = {
        "PRIME": slice_stats(
            [
                t
                for t in per_ticker
                if t.get("opening_setup") == "PRIME" and not t.get("no_track_data")
            ]
        ),
        "WATCH": slice_stats(
            [
                t
                for t in per_ticker
                if t.get("opening_setup") == "WATCH" and not t.get("no_track_data")
            ]
        ),
        "SKIP": slice_stats(
            [
                t
                for t in per_ticker
                if t.get("opening_setup") == "SKIP" and not t.get("no_track_data")
            ]
        ),
    }

    return {
        "schema_version": GRADE_SCHEMA_VERSION,
        "date": str(today),
        "decision_source": decision_source,
        "capture_phase": session_meta.get("capture_phase"),
        "capture_valid_for_opening_prediction": session_meta.get(
            "capture_valid_for_opening_prediction"
        ),
        "capture_confidence": session_meta.get("capture_confidence"),
        "data_quality": data_quality,
        "tickers_screened": len(candidates),
        "tickers_tracked": len(tracked),
        "entry_range_hit_rate": rate(tracked, "entry_range_hit"),
        "trend_accuracy_T5": rate(tracked, "trend_T5"),
        "trend_accuracy_T15": rate(tracked, "trend_T15"),
        "trend_accuracy_T30": rate(tracked, "trend_T30"),
        "clean_trade_rate": rate(tracked, "clean_trade"),
        # Champion KPI slices
        "by_signal_band": by_signal_band,
        "by_screen_result": by_screen_result,
        "by_trade_setup_action": by_trade_setup_action,
        # Legacy secondary (kept for tune/prompt compatibility)
        "by_opening_setup": by_opening_setup,
        "by_opening_setup_legacy": by_opening_setup,
        "iep_accuracy": {
            "mean_error_pct": round(sum(iep_errors) / len(iep_errors), 3)
            if iep_errors
            else None,
            "max_error_pct": round(max(iep_errors), 3) if iep_errors else None,
        },
        "config_snapshot": config_snapshot,
        "per_ticker": per_ticker,
    }


def _compute_data_quality(snapshot: dict, tracked: list[dict]) -> dict:
    source_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    for row in tracked:
        source = row.get("opening_price_source") or "missing"
        confidence = row.get("opening_price_confidence") or "NONE"
        source_counts[source] = source_counts.get(source, 0) + 1
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1

    capture_valid = snapshot.get("capture_valid_for_opening_prediction")
    if capture_valid is None:
        capture_valid = snapshot.get("is_ncp_locked")

    return {
        "capture_phase": snapshot.get("capture_phase"),
        "capture_valid_for_opening_prediction": bool(capture_valid)
        if capture_valid is not None
        else None,
        "capture_confidence": snapshot.get("capture_confidence"),
        "price_source_counts": source_counts,
        "price_confidence_counts": confidence_counts,
        "high_confidence_price_count": confidence_counts.get("HIGH", 0),
        "medium_confidence_price_count": confidence_counts.get("MEDIUM", 0),
        "low_confidence_price_count": confidence_counts.get("LOW", 0),
        "none_confidence_price_count": confidence_counts.get("NONE", 0),
        "invalid_snapshot": capture_valid is False,
    }


def _extract_observed_price(tdata) -> tuple[float, str, str] | None:
    if not isinstance(tdata, dict):
        return None

    if tdata.get("opening_price") is not None:
        return (
            float(tdata["opening_price"]),
            tdata.get("opening_price_source") or "opening_price",
            tdata.get("opening_price_confidence") or "MEDIUM",
        )

    order_book = tdata.get("order_book")
    if isinstance(order_book, dict) and order_book.get("last_price") is not None:
        return (
            float(order_book["last_price"]),
            "order_book_lastprice",
            "MEDIUM",
        )

    if tdata.get("mid_price") is not None:
        return (
            float(tdata["mid_price"]),
            tdata.get("mid_price_source") or "top_of_book_midpoint",
            tdata.get("mid_price_confidence") or "LOW",
        )

    return None


def _write_grade_md(grade: dict, path: Path) -> None:
    lines = [
        f"# Opening Session Accuracy — {grade['date']}",
        "",
        (
            f"**Tickers screened:** {grade['tickers_screened']} | "
            f"**Tracked:** {grade['tickers_tracked']} | "
            f"**Decision source:** {grade.get('decision_source', 'n/a')}"
        ),
        "",
        "## Session Summary (champion plan metrics)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Entry range hit rate | {_pct(grade.get('entry_range_hit_rate'))} |",
        f"| Trend accuracy T+5m | {_pct(grade.get('trend_accuracy_T5'))} |",
        f"| Trend accuracy T+15m | {_pct(grade.get('trend_accuracy_T15'))} |",
        f"| Trend accuracy T+30m | {_pct(grade.get('trend_accuracy_T30'))} |",
        f"| Clean trade rate | {_pct(grade.get('clean_trade_rate'))} |",
        f"| IEP mean error | {grade['iep_accuracy'].get('mean_error_pct', 'N/A')}% |",
        f"| Snapshot phase | {grade.get('data_quality', {}).get('capture_phase', 'N/A')} |",
        (
            f"| High-confidence prices | "
            f"{grade.get('data_quality', {}).get('high_confidence_price_count', 0)} |"
        ),
        (
            f"| Low-confidence prices | "
            f"{grade.get('data_quality', {}).get('low_confidence_price_count', 0)} |"
        ),
        "",
        "## By Signal Band (champion)",
        "",
        "| Band | Count | Entry Range Hit | Clean Trade | Trend T+5 | Trend T+30 |",
        "|---|---|---|---|---|---|",
    ]
    for band in ("strong", "moderate", "weak", "_missing", "_other"):
        v = grade.get("by_signal_band", {}).get(band)
        if not v:
            continue
        lines.append(
            f"| {band} | {v.get('count', 0)} "
            f"| {_pct(v.get('entry_range_hit_rate'))} "
            f"| {_pct(v.get('clean_trade_rate'))} "
            f"| {_pct(v.get('trend_accuracy_T5'))} "
            f"| {_pct(v.get('trend_accuracy_T30'))} |"
        )

    lines += [
        "",
        "## By Screen Result (funnel)",
        "",
        "| screen_result | Count | Entry Range Hit | Clean Trade |",
        "|---|---|---|---|",
    ]
    for key, v in (grade.get("by_screen_result") or {}).items():
        if not v or v.get("count", 0) == 0:
            continue
        lines.append(
            f"| {key} | {v.get('count', 0)} "
            f"| {_pct(v.get('entry_range_hit_rate'))} "
            f"| {_pct(v.get('clean_trade_rate'))} |"
        )

    lines += [
        "",
        "## By TradeSetup Action",
        "",
        "| Action | Count | Entry Range Hit | Clean Trade |",
        "|---|---|---|---|",
    ]
    for key, v in (grade.get("by_trade_setup_action") or {}).items():
        if not v or v.get("count", 0) == 0:
            continue
        lines.append(
            f"| {key} | {v.get('count', 0)} "
            f"| {_pct(v.get('entry_range_hit_rate'))} "
            f"| {_pct(v.get('clean_trade_rate'))} |"
        )

    lines += [
        "",
        "## By Opening Setup (legacy secondary — not champion KPI)",
        "",
        "| Opening Setup | Count | Entry Range Hit | Clean Trade | Trend T+5 | Trend T+30 |",
        "|---|---|---|---|---|---|",
    ]
    for opening_setup in ("PRIME", "WATCH", "SKIP"):
        v = grade.get("by_opening_setup", {}).get(opening_setup, {})
        lines.append(
            f"| {opening_setup} | {v.get('count', 0)} "
            f"| {_pct(v.get('entry_range_hit_rate'))} "
            f"| {_pct(v.get('clean_trade_rate'))} "
            f"| {_pct(v.get('trend_accuracy_T5'))} "
            f"| {_pct(v.get('trend_accuracy_T30'))} |"
        )

    lines += [
        "",
        "## Per Ticker",
        "",
        (
            "| Ticker | Sig | Action | screen_result | Trend | Opening | "
            "Entry Range | Clean | Trend T5 |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for t in grade.get("per_ticker", []):
        if t.get("no_track_data"):
            lines.append(
                f"| {t['ticker']} | {t.get('signal_score', '—')} | "
                f"{t.get('trade_setup_action') or '—'} | "
                f"{t.get('screen_result') or '—'} | — | NO DATA | — | — | — |"
            )
        else:
            lines.append(
                f"| {t['ticker']} "
                f"| {t.get('signal_score', '—')} "
                f"| {t.get('trade_setup_action') or '—'} "
                f"| {t.get('screen_result') or '—'} "
                f"| {t.get('trend', '?')} "
                f"| {t.get('opening_price', '?')} "
                f"| {'✓' if t.get('entry_range_hit') else '✗'} "
                f"| {_bool(t.get('clean_trade'))} "
                f"| {_bool(t.get('trend_T5'))} |"
            )

    path.write_text("\n".join(lines))


def _pct(v) -> str:
    return f"{v*100:.1f}%" if v is not None else "N/A"


def _bool(v) -> str:
    if v is None:
        return "—"
    return "✓" if v else "✗"
