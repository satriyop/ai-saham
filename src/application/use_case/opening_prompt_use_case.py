"""
build_prompt — generates a copy-pasteable AI prompt from the opening session data.

Pure function — reads stored JSON files, returns markdown string.
Saves to data/opening/YYYYMMDD/prompt.md.

Layer: Application
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

OPENING_DATA_DIR = Path("data/opening")


def build_prompt(run_date: date | None = None) -> str:
    today = run_date or date.today()
    day_dir = OPENING_DATA_DIR / today.strftime("%Y%m%d")

    snapshot_path = day_dir / "snapshot.json"
    grade_path = day_dir / "grade.json"

    if not snapshot_path.exists():
        raise FileNotFoundError(f"snapshot.json not found at {snapshot_path}")

    with open(snapshot_path) as f:
        snapshot = json.load(f)

    grade: dict = {}
    if grade_path.exists():
        with open(grade_path) as f:
            grade = json.load(f)

    config = grade.get("config_snapshot", {})

    lines = [
        "# Pre-Open Screener Accuracy Analysis — Copy-Paste Prompt",
        f"**Date:** {today}",
        "",
        "---",
        "",
        "## Context",
        "",
        "This is accuracy data from an automated pre-open screener for Indonesia Stock Exchange (IDX/IHSG).",
        "The screener runs at 08:57 WIB (NCP-locked window) and predicts:",
        "- Which stocks to watch at the 09:00 WIB opening auction",
        "- Entry price ranges based on ATR (Average True Range)",
        "- Trend direction (BULLISH/BEARISH/GAP_OUT/NEUTRAL)",
        "- Opening Setup: PRIME (highest conviction) / WATCH / SKIP",
        "",
        "**1R = entry_price - atr_stop** (risk unit). clean_trade = 1R available without stop being hit first.",
        "",
        "---",
        "",
        "## Pre-Open Screener Predictions (08:57 WIB, NCP-locked)",
        "",
        "| Ticker | IEV | IEP | Entry Range | Trend | RSI | Accum | IEV Intensity | Opening Setup |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for c in snapshot.get("candidates", []):
        lines.append(
            f"| {c.get('ticker')} "
            f"| {c.get('iev','?'):,} "
            f"| {c.get('iep','?')} "
            f"| {c.get('entry_range_low','?')}–{c.get('entry_range_high','?')} "
            f"| {c.get('trend','?')} "
            f"| {c.get('rsi','?')} "
            f"| {c.get('opening_broker_backing_tag','?')} "
            f"| {c.get('iev_intensity','?')} "
            f"| **{c.get('opening_setup','?')}** |"
        )

    if grade:
        lines += [
            "",
            "---",
            "",
            "## Actual Opening Session Outcomes (09:00–09:30 WIB)",
            "",
            "| Ticker | Opening Setup | Opening Price | Entry Range Hit | 1R Available | Stop Hit | Clean Trade | Trend T+5 | Trend T+30 |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for t in grade.get("per_ticker", []):
            if t.get("no_track_data"):
                lines.append(f"| {t['ticker']} | {t.get('opening_setup','?')} | NO DATA | — | — | — | — | — | — |")
            else:
                lines.append(
                    f"| {t.get('ticker')} "
                    f"| {t.get('opening_setup','?')} "
                    f"| {t.get('opening_price','?')} "
                    f"| {'✓' if t.get('entry_range_hit') else '✗'} "
                    f"| {'✓' if t.get('one_r_available') else ('✗' if t.get('one_r_available') is False else '—')} "
                    f"| {'✓' if t.get('stop_hit') else ('✗' if t.get('stop_hit') is False else '—')} "
                    f"| {'✓' if t.get('clean_trade') else ('✗' if t.get('clean_trade') is False else '—')} "
                    f"| {'✓' if t.get('trend_T5') else ('✗' if t.get('trend_T5') is False else '—')} "
                    f"| {'✓' if t.get('trend_T30') else ('✗' if t.get('trend_T30') is False else '—')} |"
                )

        lines += [
            "",
            "## Session-Level Summary",
            "",
            f"- Entry range hit rate: **{_pct(grade.get('entry_range_hit_rate'))}**",
            f"- Trend accuracy T+5:   **{_pct(grade.get('trend_accuracy_T5'))}**",
            f"- Trend accuracy T+15:  **{_pct(grade.get('trend_accuracy_T15'))}**",
            f"- Trend accuracy T+30:  **{_pct(grade.get('trend_accuracy_T30'))}**",
            f"- Clean trade rate:     **{_pct(grade.get('clean_trade_rate'))}**",
            f"- IEP mean error:       **{grade.get('iep_accuracy',{}).get('mean_error_pct','N/A')}%**",
            "",
            "**By opening setup:**",
        ]
        for opening_setup in ("PRIME", "WATCH", "SKIP"):
            v = grade.get("by_opening_setup", {}).get(opening_setup, {})
            lines.append(
                f"- {opening_setup}: count={v.get('count',0)} | "
                f"entry_hit={_pct(v.get('entry_range_hit_rate'))} | "
                f"clean_trade={_pct(v.get('clean_trade_rate'))}"
            )

    if config:
        lines += [
            "",
            "## Current Screener Config",
            "",
            "```yaml",
        ]
        for k, v in config.items():
            lines.append(f"  {k}: {v}")
        lines.append("```")

    lines += [
        "",
        "---",
        "",
        "## Your Task",
        "",
        "Based on the accuracy data above, please:",
        "",
        "1. Identify the most significant accuracy problem (selection vs. positioning vs. both)",
        "2. Suggest specific config parameter changes with evidence-based reasoning",
        "3. Note any IDX-specific patterns you observe (e.g. IEV manipulation, trend fade timing)",
        "4. Rate confidence in each recommendation (high/medium/low)",
        "",
        "Format recommendations as: `parameter_name: current_value → suggested_value — reason`",
    ]

    prompt = "\n".join(lines)
    (day_dir / "prompt.md").write_text(prompt)
    return prompt


def _pct(v) -> str:
    return f"{v*100:.1f}%" if v is not None else "N/A"
