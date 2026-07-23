#!/usr/bin/env python3
"""Factor card: foreign VWAP discount × market regime (Package A / B follow-up).

Research only — authority NONE.

Answers whether deep foreign VWAP edge is regime-conditional (esp. RISK_OFF /
soft markets) vs a global foreign-bounce gate hike.

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_vwap_buckets.py
  .venv/bin/python research/scripts/factor_card_vwap_buckets.py --out research/artifacts/factor_card_vwap_regime_schema7.md
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

REGIME_ORDER = ("RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE", "UNKNOWN")


def _norm_regime(regime: str | None) -> str:
    if not regime:
        return "UNKNOWN"
    return str(regime).upper()


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
    hit = f"{stats['hit_pct']:.1f}" if stats["hit_pct"] is not None else "—"
    avg = f"{stats['avg_ret']:+.2f}" if stats["avg_ret"] is not None else "—"
    pf = f"{stats['pf']:.2f}" if stats["pf"] is not None else "—"
    return f"{n} | {hit} | {avg} | {pf}"


def build_report(panel: list[PanelRow], db_path: Path) -> str:
    with_vwap = [r for r in panel if r.vwap_discount_pct is not None]
    missing = len(panel) - len(with_vwap)
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"

    by_regime: dict[str, list[PanelRow]] = defaultdict(list)
    for r in with_vwap:
        by_regime[_norm_regime(r.regime)].append(r)

    lines: list[str] = [
        "# Factor Card — VWAP Discount × Regime",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical obs ⋈ SWING_10D labels",
        f"- Rows: {len(panel)} total; {len(with_vwap)} with `vwap_discount_pct`; "
        f"{missing} missing VWAP",
        f"- Snapshot span: {date_span}",
        "",
        "## Hypothesis",
        "",
        "Deeper foreign VWAP discount improves SWING_10D outcomes **only in "
        "some regimes** (esp. RISK_OFF / soft markets). A global foreign-bounce "
        "VWAP hike (3→8/10) is the wrong promotion if RISK_ON deep-VWAP is weak.",
        "",
        "## Baseline by regime (all VWAP present)",
        "",
        "| Regime | n | Hit % | Avg close ret % | PF |",
        "|--------|---|-------|-----------------|----|",
    ]
    for regime in REGIME_ORDER:
        rows = by_regime.get(regime, [])
        if not rows:
            continue
        lines.append(f"| {regime} | {_fmt(_stats(rows))} |")
    lines.append(f"| All with VWAP | {_fmt(_stats(with_vwap))} |")
    lines.append("")

    # Primary: gate × regime matrix
    lines.extend(
        [
            "## Primary: VWAP gate × regime",
            "",
            "Each cell = rows with `vwap_discount_pct ≥ threshold` in that regime.",
            "",
        ]
    )
    for thr_label, thr in GATES:
        lines.extend(
            [
                f"### {thr_label}",
                "",
                "| Regime | n | Hit % | Avg % | PF |",
                "|--------|---|-------|-------|----|",
            ]
        )
        for regime in REGIME_ORDER:
            rows = [
                r
                for r in by_regime.get(regime, [])
                if (r.vwap_discount_pct or 0.0) >= thr
            ]
            if not rows and regime not in by_regime:
                continue
            lines.append(f"| {regime} | {_fmt(_stats(rows))} |")
        all_thr = [r for r in with_vwap if (r.vwap_discount_pct or 0.0) >= thr]
        lines.append(f"| All | {_fmt(_stats(all_thr))} |")
        lines.append("")

    # Deep vs shallow within regime
    lines.extend(
        [
            "## Deep vs shallow within regime",
            "",
            "Deep = VWAP ≥ 8%. Shallow = VWAP < 3% (includes over-VWAP).",
            "",
            "| Regime | Deep n | Deep hit% | Deep avg% | Shallow n | "
            "Shallow hit% | Shallow avg% | Δ hit pp |",
            "|--------|--------|-----------|-----------|-----------|"
            "--------------|--------------|----------|",
        ]
    )
    for regime in REGIME_ORDER:
        rows = by_regime.get(regime, [])
        if not rows:
            continue
        deep = [r for r in rows if (r.vwap_discount_pct or 0.0) >= 8.0]
        shallow = [r for r in rows if (r.vwap_discount_pct or 0.0) < 3.0]
        ds, ss = _stats(deep), _stats(shallow)
        d_hit = ds["hit_pct"]
        s_hit = ss["hit_pct"]
        delta = None
        if d_hit is not None and s_hit is not None:
            delta = float(d_hit) - float(s_hit)
        d_avg = (
            f"{ds['avg_ret']:+.2f}" if ds["avg_ret"] is not None else "—"
        )
        s_avg = (
            f"{ss['avg_ret']:+.2f}" if ss["avg_ret"] is not None else "—"
        )
        d_hit_s = f"{d_hit:.1f}" if d_hit is not None else "—"
        s_hit_s = f"{s_hit:.1f}" if s_hit is not None else "—"
        delta_s = f"{delta:+.1f}" if delta is not None else "—"
        lines.append(
            f"| {regime} | {ds['n']} | {d_hit_s} | {d_avg} | {ss['n']} | "
            f"{s_hit_s} | {s_avg} | {delta_s} |"
        )
    lines.append("")

    # Global buckets (context)
    lines.extend(
        [
            "## Global bucket view (all regimes pooled)",
            "",
            "| Bucket | n | Hit % | Avg close ret % | PF |",
            "|--------|---|-------|-----------------|----|",
        ]
    )
    for label, low, high in BUCKETS:
        subset = [
            r
            for r in with_vwap
            if _in_bucket(r.vwap_discount_pct or 0.0, low, high)
        ]
        lines.append(f"| {label} | {_fmt(_stats(subset))} |")
    lines.append("")

    # Buckets within NEUTRAL / RISK_OFF (main mass)
    for regime in ("NEUTRAL", "RISK_OFF", "RISK_ON"):
        rows = by_regime.get(regime, [])
        if not rows:
            continue
        lines.extend(
            [
                f"## Bucket view — {regime} only",
                "",
                "| Bucket | n | Hit % | Avg % | PF |",
                "|--------|---|-------|-------|----|",
            ]
        )
        for label, low, high in BUCKETS:
            subset = [
                r
                for r in rows
                if _in_bucket(r.vwap_discount_pct or 0.0, low, high)
            ]
            lines.append(f"| {label} | {_fmt(_stats(subset))} |")
        lines.append("")

    # Optional high-coverage overlay for deep VWAP
    high_cov = [
        r
        for r in with_vwap
        if r.signal_authority_coverage is not None
        and r.signal_authority_coverage >= 0.70
    ]
    lines.extend(
        [
            "## Overlay: deep VWAP (≥8%) with cov≥0.70",
            "",
            f"High-coverage rows with VWAP: {len(high_cov)} / {len(with_vwap)}.",
            "",
            "| Regime | n | Hit % | Avg % | PF |",
            "|--------|---|-------|-------|----|",
        ]
    )
    for regime in REGIME_ORDER:
        rows = [
            r
            for r in high_cov
            if _norm_regime(r.regime) == regime
            and (r.vwap_discount_pct or 0.0) >= 8.0
        ]
        if not rows and regime not in by_regime:
            continue
        lines.append(f"| {regime} | {_fmt(_stats(rows))} |")
    lines.append(
        f"| All high-cov ≥8% | {_fmt(_stats([r for r in high_cov if (r.vwap_discount_pct or 0.0) >= 8.0]))} |"
    )
    lines.append("")

    lines.extend(
        [
            "## Interpretation guardrails",
            "",
            "- Canonical panel only; quarantine excluded. Authority NONE.",
            "- Synthetic soft filter ≠ foreign-bounce MATCH (B2 showed MATCH is weak).",
            "- Short span → hypothesis generation, not promotion proof.",
            "- Prefer regime-conditional use over a global 3→10 gate hike.",
            "- RISK_ON deep-VWAP with negative avg return argues **against** "
            "all-regime tightening.",
            "",
            "## Proposed config / product action",
            "",
            "**None automatic.** Candidate follow-ups (human review):",
            "- If NEUTRAL/RISK_OFF deep VWAP stays strong and RISK_ON stays weak: "
            "soft Disc% filter or regime-conditioned screen sort — not YAML MATCH hike",
            "- Do not change `swing_setups.yaml` foreign-bounce `min_vwap_discount_pct` "
            "from this card alone",
            "- Next: soft VWAP UX on screen, or Package C risk-gate persistence",
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
            / f"factor_card_vwap_regime_{date.today().isoformat()}.md"
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
