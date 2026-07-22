#!/usr/bin/env python3
"""Factor card: Accum / foreign-flow component ablation (Package A1).

Research only — authority NONE.

For each feeder component (consistency, streak, VWAP, RSI, flow%, BCI/inst):
- high vs low split on raw input and on awarded points
- Pearson corr(points, close_return)
- crude leave-one-out: outcomes when full score is high vs score-without-component high

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_accum_components.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from math import sqrt
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lab.panel import PanelRow, load_swing10d_panel, resolve_db_path

# (label, raw_attr, points_attr, without_attr)
COMPONENTS: list[tuple[str, str, str, str]] = [
    ("consistency (net_buy_ratio)", "net_buy_ratio", "points_cons", "score_without_cons"),
    ("streak (consecutive_streak)", "consecutive_streak", "points_streak", "score_without_streak"),
    ("vwap_discount_pct", "vwap_discount_pct", "points_vwap", "score_without_vwap"),
    ("rsi_headroom (rsi)", "rsi", "points_rsi", "score_without_rsi"),
    ("flow% (avg_flow_ratio)", "avg_flow_ratio", "points_flow", "score_without_flow"),
    ("bci / inst (label→points)", "foreign_flow_score", "points_inst", "score_without_inst"),
]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 5:
        return None
    mx = mean(xs)
    my = mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _stats(rows: list[PanelRow]) -> dict[str, float | int | None]:
    n = len(rows)
    if n == 0:
        return {"n": 0, "hit_pct": None, "avg_ret": None, "pf": None}
    successes = sum(1 for r in rows if r.outcome_label == "SUCCESS")
    returns = [r.close_return for r in rows if r.close_return is not None]
    avg_ret = mean(returns) if returns else None
    wins = [x for x in returns if x > 0]
    losses = [x for x in returns if x < 0]
    gross_loss = abs(sum(losses))
    pf = (sum(wins) / gross_loss) if gross_loss > 0 else None
    return {
        "n": n,
        "hit_pct": 100.0 * successes / n,
        "avg_ret": avg_ret,
        "pf": pf,
    }


def _fmt(stats: dict[str, float | int | None]) -> str:
    n = stats["n"]
    if not n:
        return "0 | — | — | —"
    hit = stats["hit_pct"]
    avg = stats["avg_ret"]
    pf = stats["pf"]
    hit_s = f"{hit:.1f}" if hit is not None else "—"
    avg_s = f"{avg:+.2f}" if avg is not None else "—"
    pf_s = f"{pf:.2f}" if pf is not None else "—"
    return f"{n} | {hit_s} | {avg_s} | {pf_s}"


def _attr(row: PanelRow, name: str) -> float | None:
    value = getattr(row, name, None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _high_low(
    panel: list[PanelRow], attr: str
) -> tuple[list[PanelRow], list[PanelRow], float | None]:
    pairs = [(row, _attr(row, attr)) for row in panel]
    pairs = [(r, v) for r, v in pairs if v is not None]
    if len(pairs) < 10:
        return [], [], None
    values = [v for _, v in pairs]
    med = median(values)
    # If median sits on a mass point (e.g. streak mostly 0), split strictly above.
    if sum(1 for v in values if v == med) > 0.6 * len(values):
        high = [r for r, v in pairs if v > med]
        low = [r for r, v in pairs if v <= med]
    else:
        high = [r for r, v in pairs if v >= med]
        low = [r for r, v in pairs if v < med]
    if not high or not low:
        # Fall back to >= / < even if unbalanced.
        high = [r for r, v in pairs if v >= med]
        low = [r for r, v in pairs if v < med]
    return high, low, med


def build_report(panel: list[PanelRow], db_path: Path) -> str:
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"
    baseline = _stats(panel)

    lines: list[str] = [
        "# Factor Card — Accum Component Ablation (A1)",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical `candidate_observations` ⋈ `signal_forward_labels` "
        f"(horizon=`SWING_10D`)",
        f"- Rows: {len(panel)}",
        f"- Snapshot span: {date_span}",
        "- Component points from `foreign_flow_score_breakdown.breakdown`",
        "- Leave-one-out proxy: `foreign_flow_score − component_points` "
        "(additive reconstruction; ignores renormalization edge cases)",
        "",
        "## Hypothesis",
        "",
        "Each Accum feeder component should show measurable association with "
        "SWING_10D outcomes. Components with flat/negative high−low Δ or weak "
        "corr are candidates to weaken or make conditional — not automatic YAML edits.",
        "",
        f"## Baseline",
        "",
        "| Cohort | n | Hit % | Avg close ret % | PF |",
        "|--------|---|-------|-----------------|----|",
        f"| All panel | {_fmt(baseline)}",
        "",
        "## Raw inputs — high vs low (median split)",
        "",
        "| Component input | median | High n | High hit% | High avg% | Low n | Low hit% | Low avg% | Δ avg |",
        "|-----------------|--------|--------|-----------|-----------|-------|----------|----------|-------|",
    ]

    for label, raw_attr, _points, _without in COMPONENTS:
        if label.startswith("bci"):
            continue
        high, low, med = _high_low(panel, raw_attr)
        if med is None:
            lines.append(f"| {label} | — | — | — | — | — | — | — | — |")
            continue
        hs, ls = _stats(high), _stats(low)
        d_avg = None
        if hs["avg_ret"] is not None and ls["avg_ret"] is not None:
            d_avg = float(hs["avg_ret"]) - float(ls["avg_ret"])
        d_s = f"{d_avg:+.2f}" if d_avg is not None else "—"
        h_hit = f"{hs['hit_pct']:.1f}" if hs["hit_pct"] is not None else "—"
        l_hit = f"{ls['hit_pct']:.1f}" if ls["hit_pct"] is not None else "—"
        h_avg = f"{hs['avg_ret']:+.2f}" if hs["avg_ret"] is not None else "—"
        l_avg = f"{ls['avg_ret']:+.2f}" if ls["avg_ret"] is not None else "—"
        lines.append(
            f"| {label} | {med:g} | {hs['n']} | {h_hit} | {h_avg} | "
            f"{ls['n']} | {l_hit} | {l_avg} | {d_s} |"
        )

    lines.extend(
        [
            "",
            "## Component points — corr + high vs low",
            "",
            "| Component points | n | corr(points, ret) | High avg % | Low avg % | Δ avg | High PF | Low PF |",
            "|------------------|---|-------------------|------------|-----------|-------|---------|--------|",
        ]
    )

    for label, _raw, points_attr, _without in COMPONENTS:
        high, low, med = _high_low(panel, points_attr)
        pairs = [
            (_attr(r, points_attr), r.close_return)
            for r in panel
            if _attr(r, points_attr) is not None and r.close_return is not None
        ]
        if not pairs:
            lines.append(f"| {label} | 0 | — | — | — | — | — | — |")
            continue
        corr = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
        hs, ls = _stats(high), _stats(low)
        d_avg = None
        if hs["avg_ret"] is not None and ls["avg_ret"] is not None:
            d_avg = float(hs["avg_ret"]) - float(ls["avg_ret"])
        corr_s = f"{corr:+.3f}" if corr is not None else "—"
        high_avg = f"{hs['avg_ret']:+.2f}" if hs["avg_ret"] is not None else "—"
        low_avg = f"{ls['avg_ret']:+.2f}" if ls["avg_ret"] is not None else "—"
        d_s = f"{d_avg:+.2f}" if d_avg is not None else "—"
        hpf = f"{hs['pf']:.2f}" if hs["pf"] is not None else "—"
        lpf = f"{ls['pf']:.2f}" if ls["pf"] is not None else "—"
        lines.append(
            f"| {label} | {len(pairs)} | {corr_s} | {high_avg} | {low_avg} | {d_s} | {hpf} | {lpf} |"
        )

    lines.extend(
        [
            "",
            "## Leave-one-out proxy (score without component)",
            "",
            "Compare rows where **full score** is above its median vs where "
            "**score−component** is above its median. If removing a component "
            "improves the high-bucket avg return, that component may be dilutive.",
            "",
            "| Dropped component | Full-score high avg % | Without-comp high avg % | Δ (without − full) |",
            "|-------------------|----------------------|-------------------------|--------------------|",
        ]
    )

    full_high, _, _ = _high_low(panel, "foreign_flow_score")
    full_stats = _stats(full_high)
    full_avg = full_stats["avg_ret"]

    for label, _raw, _points, without_attr in COMPONENTS:
        high, _, med = _high_low(panel, without_attr)
        if med is None:
            lines.append(f"| {label} | — | — | — |")
            continue
        ws = _stats(high)
        d = None
        if ws["avg_ret"] is not None and full_avg is not None:
            d = float(ws["avg_ret"]) - float(full_avg)
        full_s = f"{full_avg:+.2f}" if full_avg is not None else "—"
        with_s = f"{ws['avg_ret']:+.2f}" if ws["avg_ret"] is not None else "—"
        d_s = f"{d:+.2f}" if d is not None else "—"
        lines.append(f"| {label} | {full_s} | {with_s} | {d_s} |")

    # BCI categorical reminder
    cluster = [r for r in panel if (r.bci_label or "").upper() == "CLUSTER"]
    non_cluster = [r for r in panel if (r.bci_label or "").upper() != "CLUSTER"]
    lines.extend(
        [
            "",
            "## BCI label quick check",
            "",
            "| Cohort | n | Hit % | Avg % | PF |",
            "|--------|---|-------|-------|----|",
            f"| CLUSTER | {_fmt(_stats(cluster))}",
            f"| non-CLUSTER | {_fmt(_stats(non_cluster))}",
            "",
            "## Interpretation guardrails",
            "",
            "- Canonical panel only; short span → provisional keep/weaken signals.",
            "- RSI is in the composite Accum score but excluded from Signal flow "
            "sub-signals — interpret RSI row as feeder honesty, not flow-group authority.",
            "- BB squeeze disabled in policy — omitted here.",
            "- Positive Δ avg (high−low) supports keeping/strengthening; negative "
            "suggests weaken or condition (see A2 for BCI×flow sign).",
            "- Leave-one-out is a heuristic, not a formal Shapley attribution.",
            "",
            "## Proposed config action",
            "",
            "**None automatic.** Use this card to shortlist components for:",
            "- weight down / saturate_at changes in `config/accumulation_screener.yaml`",
            "- conditional BCI (A2) before touching `cluster_points`",
            "- deeper A3 (sector bonus) / A4 (broker lists) cards next within Package A",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    panel = load_swing10d_panel(db_path)
    report = build_report(panel, db_path)

    out = args.out
    if out is None:
        out = (
            ROOT
            / "research"
            / "artifacts"
            / f"factor_card_accum_components_{date.today().isoformat()}.md"
        )
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
