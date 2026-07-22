#!/usr/bin/env python3
"""Factor card: foreign VWAP discount buckets vs SWING_10D outcomes.

Package A (Accum feeder) — research only, authority NONE.

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_vwap_buckets.py
  .venv/bin/python research/scripts/factor_card_vwap_buckets.py --db data/db/data.db
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lab.panel import PanelRow, load_swing10d_panel, resolve_db_path

BUCKETS: list[tuple[str, float | None, float | None]] = [
    ("< 0% (over VWAP)", None, 0.0),
    ("0–3%", 0.0, 3.0),
    ("3–5%", 3.0, 5.0),
    ("5–7%", 5.0, 7.0),
    ("7–10%", 7.0, 10.0),
    ("10–15%", 10.0, 15.0),
    (">= 15%", 15.0, None),
]

GATES: list[tuple[str, float]] = [
    (">= 3% (current FB gate)", 3.0),
    (">= 5%", 5.0),
    (">= 8%", 8.0),
    (">= 10%", 10.0),
]


def _in_bucket(vwap: float, low: float | None, high: float | None) -> bool:
    if low is not None and vwap < low:
        return False
    if high is not None and vwap >= high:
        return False
    return True


def _stats(rows: list[PanelRow]) -> dict[str, float | int | None]:
    n = len(rows)
    if n == 0:
        return {"n": 0, "hit_pct": None, "avg_ret": None, "pf": None}
    successes = sum(1 for r in rows if r.outcome_label == "SUCCESS")
    returns = [r.close_return for r in rows if r.close_return is not None]
    avg_ret = mean(returns) if returns else None
    wins = [x for x in returns if x is not None and x > 0]
    losses = [x for x in returns if x is not None and x < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else None
    return {
        "n": n,
        "hit_pct": 100.0 * successes / n,
        # close_return is already stored as percent points (e.g. 1.55 = +1.55%).
        "avg_ret": avg_ret,
        "pf": pf,
    }


def _fmt(stats: dict[str, float | int | None]) -> str:
    n = stats["n"]
    if not n:
        return "| 0 | — | — | — |"
    hit = stats["hit_pct"]
    avg = stats["avg_ret"]
    pf = stats["pf"]
    hit_s = f"{hit:.1f}" if hit is not None else "—"
    avg_s = f"{avg:+.2f}" if avg is not None else "—"
    pf_s = f"{pf:.2f}" if pf is not None else "—"
    return f"| {n} | {hit_s} | {avg_s} | {pf_s} |"


def build_report(panel: list[PanelRow], db_path: Path) -> str:
    with_vwap = [r for r in panel if r.vwap_discount_pct is not None]
    missing = len(panel) - len(with_vwap)
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"

    lines: list[str] = [
        "# Factor Card — VWAP Discount Buckets",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical `candidate_observations` ⋈ `signal_forward_labels` "
        f"(horizon=`SWING_10D`)",
        f"- Rows: {len(panel)} total; {len(with_vwap)} with `vwap_discount_pct`; "
        f"{missing} missing VWAP",
        f"- Snapshot span: {date_span}",
        "",
        "## Hypothesis",
        "",
        "Deeper foreign VWAP discount (price below foreign VWAP) improves "
        "SWING_10D hit rate / average close return versus shallow discounts.",
        "Current foreign-bounce gate uses `min_vwap_discount_pct = 3.0`.",
        "",
        "## Bucket view",
        "",
        "| Bucket | n | Hit % (SUCCESS) | Avg close ret % | Profit factor |",
        "|--------|---|-----------------|-----------------|---------------|",
    ]

    for label, low, high in BUCKETS:
        subset = [
            r
            for r in with_vwap
            if _in_bucket(r.vwap_discount_pct or 0.0, low, high)
        ]
        lines.append(f"| {label} {_fmt(_stats(subset))}")

    lines.extend(
        [
            "",
            "## Cumulative gate sweep",
            "",
            "| Gate | n | Hit % | Avg close ret % | Profit factor |",
            "|------|---|-------|-----------------|---------------|",
        ]
    )
    for label, thr in GATES:
        subset = [r for r in with_vwap if (r.vwap_discount_pct or 0.0) >= thr]
        lines.append(f"| {label} {_fmt(_stats(subset))}")

    # Regime-stratified for >=8% and >=10%
    lines.extend(
        [
            "",
            "## Regime-stratified (deep VWAP)",
            "",
            "Regime from `regime_observations` on snapshot date "
            "(missing regime counted as `UNKNOWN`).",
            "",
        ]
    )
    for thr_label, thr in ((">= 8%", 8.0), (">= 10%", 10.0)):
        lines.append(f"### VWAP {thr_label}")
        lines.append("")
        lines.append(
            "| Regime | n | Hit % | Avg close ret % | Profit factor |"
        )
        lines.append("|--------|---|-------|-----------------|---------------|")
        by_regime: dict[str, list[PanelRow]] = defaultdict(list)
        for r in with_vwap:
            if (r.vwap_discount_pct or 0.0) >= thr:
                by_regime[r.regime or "UNKNOWN"].append(r)
        for regime in sorted(by_regime):
            lines.append(f"| {regime} {_fmt(_stats(by_regime[regime]))}")
        lines.append("")

    baseline = _stats(panel)
    lines.extend(
        [
            "## Baseline (all panel rows)",
            "",
            "| Cohort | n | Hit % | Avg close ret % | Profit factor |",
            "|--------|---|-------|-----------------|---------------|",
            f"| All SWING_10D {_fmt(baseline)}",
            "",
            "## Interpretation guardrails",
            "",
            "- Canonical panel only; quarantine tables excluded.",
            "- Labels are raw-market (`outcome_basis` contract), not net-executable.",
            "- Short snapshot span → treat as hypothesis generation, not promotion proof.",
            "- Prefer regime-conditional conclusions over a global gate hike.",
            "- Next: Package A2 BCI×flow-sign card; Package D MCE factor card.",
            "",
            "## Proposed config action",
            "",
            "**None automatic.** If deep VWAP looks better only in RISK_OFF, propose a "
            "`decision_policy` / setup-regime conditional rule — do not silently edit "
            "`config/swing_setups.yaml`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to data.db (default: data/db/data.db)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output markdown path (default: research/artifacts/factor_card_vwap_*.md)",
    )
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    panel = load_swing10d_panel(db_path)
    report = build_report(panel, db_path)

    out = args.out
    if out is None:
        out = ROOT / "research" / "artifacts" / f"factor_card_vwap_{date.today().isoformat()}.md"
    else:
        out = out.expanduser()
        if not out.is_absolute():
            out = Path.cwd() / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
