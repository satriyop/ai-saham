"""
opening_grade — deterministic accuracy analysis for the opening session learning loop.

Joins snapshot.json (screener predictions) with track_*.json files (actual prices)
and computes per-ticker and session-level accuracy metrics.

Pure function — no injected dependencies, no network, no database.

Layer: Application
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

OPENING_DATA_DIR = Path("data/opening")


def compute_grade(run_date: date | None = None) -> dict:
    """
    Load today's snapshot + track files and compute accuracy report.
    Saves grade.json and grade.md. Returns the grade dict.
    """
    today = run_date or date.today()
    day_dir = OPENING_DATA_DIR / today.strftime("%Y%m%d")

    snapshot_path = day_dir / "snapshot.json"
    if not snapshot_path.exists():
        raise FileNotFoundError(f"No snapshot found at {snapshot_path}. Run `opening snapshot` first.")

    with open(snapshot_path) as f:
        snapshot = json.load(f)

    # Load all track files sorted by time
    track_files = sorted(day_dir.glob("track_*.json"))
    if not track_files:
        raise FileNotFoundError(f"No track files found in {day_dir}. Run `opening track` first.")

    tracks: list[dict] = []
    for tf in track_files:
        with open(tf) as f:
            tracks.append(json.load(f))

    candidates = snapshot.get("candidates", [])
    per_ticker = []

    for cand in candidates:
        ticker = cand["ticker"]
        suggested_entry = cand.get("suggested_entry")
        atr_stop = cand.get("atr_stop")
        one_r = cand.get("one_r")
        entry_low = cand.get("entry_range_low")
        entry_high = cand.get("entry_range_high")
        trend = cand.get("trend")
        iep = cand.get("iep")
        verdict = cand.get("verdict", "SKIP")
        bid_pressure_preopen = cand.get("bid_pressure_preopen")  # NCP-locked 08:57

        # Time-series of mid_prices for this ticker
        price_series: list[tuple[str, float]] = []
        for track in tracks:
            tdata = track.get("tickers", {}).get(ticker)
            if tdata and isinstance(tdata, dict) and "mid_price" in tdata:
                price_series.append((track["captured_at"], tdata["mid_price"]))

        bp_series: list[float] = []
        for track in tracks:
            tdata = track.get("tickers", {}).get(ticker)
            if tdata and isinstance(tdata, dict) and tdata.get("bid_pressure") is not None:
                bp_series.append(tdata["bid_pressure"])

        if not price_series:
            per_ticker.append({
                "ticker": ticker,
                "verdict": verdict,
                "trend": trend,
                "no_track_data": True,
            })
            continue

        opening_price = price_series[0][1]
        prices = [p for _, p in price_series]
        peak = max(prices)
        trough = min(prices)

        # Entry range accuracy
        entry_range_hit = (
            entry_low is not None
            and entry_high is not None
            and entry_low <= opening_price <= entry_high
        )

        # IEP accuracy
        iep_error_pct = (
            round(abs(iep - opening_price) / opening_price * 100, 3)
            if iep and opening_price
            else None
        )

        # Trend accuracy at T5, T15, T30
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

        # 1R metrics
        one_r_available = None
        stop_hit = None
        clean_trade = None
        if suggested_entry and one_r and atr_stop:
            target = suggested_entry + one_r
            one_r_available = peak >= target
            stop_hit = trough <= atr_stop
            clean_trade = one_r_available and not stop_hit

        # Bid pressure momentum
        bid_momentum = None
        if len(bp_series) >= 2:
            bid_momentum = round(bp_series[1] - bp_series[0], 4)

        # Broker confirmation signal — read from track files if --broker-confirm was used
        broker_signals: list[dict] = []
        for track in tracks:
            tdata = track.get("tickers", {}).get(ticker)
            if isinstance(tdata, dict) and isinstance(tdata.get("broker_signal"), dict):
                broker_signals.append(tdata["broker_signal"])

        institutional_absorption_rate = None
        broker_dominant_side = None
        if broker_signals:
            absorptions = [s["absorption_ratio"] for s in broker_signals if s.get("absorption_ratio") is not None]
            institutional_absorption_rate = round(sum(absorptions) / len(absorptions), 4) if absorptions else None
            # Most frequent dominant_side across snapshots
            sides = [s["dominant_side"] for s in broker_signals if s.get("dominant_side")]
            if sides:
                broker_dominant_side = max(set(sides), key=sides.count)

        per_ticker.append({
            "ticker": ticker,
            "verdict": verdict,
            "trend": trend,
            "iep": iep,
            "opening_price": opening_price,
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
            # bid_pressure signals — key for learning loop
            "bid_pressure_preopen": bid_pressure_preopen,  # 08:57 NCP-locked
            "bid_pressure_T0": bp_series[0] if bp_series else None,  # 09:00 post-open
            "bid_pressure_T5": bp_series[1] if len(bp_series) > 1 else None,  # 09:05
            "bid_momentum": bid_momentum,   # T5 - T0 (did buying pressure sustain?)
            # broker confirmation (present only when --broker-confirm was used during track)
            "institutional_absorption_rate": institutional_absorption_rate,
            "broker_dominant_side": broker_dominant_side,
            "price_series": price_series,
        })

    # Session-level aggregates
    def rate(items, key):
        vals = [t[key] for t in items if t.get(key) is not None]
        return round(sum(1 for v in vals if v) / len(vals), 3) if vals else None

    def by_verdict(verdict_filter):
        subset = [t for t in per_ticker if t.get("verdict") == verdict_filter and not t.get("no_track_data")]
        if not subset:
            return {"count": 0}
        return {
            "count": len(subset),
            "entry_range_hit_rate": rate(subset, "entry_range_hit"),
            "clean_trade_rate": rate(subset, "clean_trade"),
            "trend_accuracy_T5": rate(subset, "trend_T5"),
            "trend_accuracy_T30": rate(subset, "trend_T30"),
        }

    tracked = [t for t in per_ticker if not t.get("no_track_data")]
    iep_errors = [t["iep_error_pct"] for t in tracked if t.get("iep_error_pct") is not None]

    # Load current config snapshot
    config_snapshot = _load_config_snapshot()

    grade = {
        "date": str(today),
        "tickers_screened": len(candidates),
        "tickers_tracked": len(tracked),
        "entry_range_hit_rate": rate(tracked, "entry_range_hit"),
        "trend_accuracy_T5": rate(tracked, "trend_T5"),
        "trend_accuracy_T15": rate(tracked, "trend_T15"),
        "trend_accuracy_T30": rate(tracked, "trend_T30"),
        "clean_trade_rate": rate(tracked, "clean_trade"),
        "by_verdict": {
            "PRIME": by_verdict("PRIME"),
            "WATCH": by_verdict("WATCH"),
            "SKIP": by_verdict("SKIP"),
        },
        "iep_accuracy": {
            "mean_error_pct": round(sum(iep_errors) / len(iep_errors), 3) if iep_errors else None,
            "max_error_pct": round(max(iep_errors), 3) if iep_errors else None,
        },
        "config_snapshot": config_snapshot,
        "per_ticker": per_ticker,
    }

    # Persist
    with open(day_dir / "grade.json", "w") as f:
        json.dump(grade, f, indent=2, default=str)

    _write_grade_md(grade, day_dir / "grade.md")

    return grade


def _load_config_snapshot() -> dict:
    try:
        import yaml
        with open("config/pre_open_screener.yaml") as f:
            data = yaml.safe_load(f)
        analysis = data.get("analysis", {})
        risk = data.get("risk", {})
        return {
            "rsi_overbought_threshold": analysis.get("rsi_overbought_threshold"),
            "iev_intensity_unusual_threshold": analysis.get("iev_intensity_unusual_threshold"),
            "atr_range_cap_min": analysis.get("atr_range_cap_min"),
            "atr_range_cap_max": analysis.get("atr_range_cap_max"),
            "accum_backed_threshold": analysis.get("accum_backed_threshold"),
            "min_target_ticks": risk.get("min_target_ticks"),
            "tick_friction_gate": risk.get("tick_friction_gate"),
        }
    except Exception:
        return {}


def _write_grade_md(grade: dict, path: Path) -> None:
    lines = [
        f"# Opening Session Accuracy — {grade['date']}",
        "",
        f"**Tickers screened:** {grade['tickers_screened']} | **Tracked:** {grade['tickers_tracked']}",
        "",
        "## Session Summary",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Entry range hit rate | {_pct(grade.get('entry_range_hit_rate'))} |",
        f"| Trend accuracy T+5m | {_pct(grade.get('trend_accuracy_T5'))} |",
        f"| Trend accuracy T+15m | {_pct(grade.get('trend_accuracy_T15'))} |",
        f"| Trend accuracy T+30m | {_pct(grade.get('trend_accuracy_T30'))} |",
        f"| Clean trade rate | {_pct(grade.get('clean_trade_rate'))} |",
        f"| IEP mean error | {grade['iep_accuracy'].get('mean_error_pct', 'N/A')}% |",
        "",
        "## By Verdict",
        "",
        "| Verdict | Count | Entry Range Hit | Clean Trade | Trend T+5 | Trend T+30 |",
        "|---|---|---|---|---|---|",
    ]
    for verdict in ("PRIME", "WATCH", "SKIP"):
        v = grade["by_verdict"].get(verdict, {})
        lines.append(
            f"| {verdict} | {v.get('count', 0)} "
            f"| {_pct(v.get('entry_range_hit_rate'))} "
            f"| {_pct(v.get('clean_trade_rate'))} "
            f"| {_pct(v.get('trend_accuracy_T5'))} "
            f"| {_pct(v.get('trend_accuracy_T30'))} |"
        )

    lines += ["", "## Per Ticker", "",
              "| Ticker | Verdict | Trend | Opening | Entry Range | 1R Avail | Stop Hit | Clean | Trend T5 | Trend T30 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for t in grade.get("per_ticker", []):
        if t.get("no_track_data"):
            lines.append(f"| {t['ticker']} | {t.get('verdict','?')} | — | NO DATA | — | — | — | — | — | — |")
        else:
            lines.append(
                f"| {t['ticker']} "
                f"| {t.get('verdict','?')} "
                f"| {t.get('trend','?')} "
                f"| {t.get('opening_price','?')} "
                f"| {'✓' if t.get('entry_range_hit') else '✗'} "
                f"| {_bool(t.get('one_r_available'))} "
                f"| {_bool(t.get('stop_hit'))} "
                f"| {_bool(t.get('clean_trade'))} "
                f"| {_bool(t.get('trend_T5'))} "
                f"| {_bool(t.get('trend_T30'))} |"
            )

    path.write_text("\n".join(lines))


def _pct(v) -> str:
    return f"{v*100:.1f}%" if v is not None else "N/A"


def _bool(v) -> str:
    if v is None:
        return "—"
    return "✓" if v else "✗"
