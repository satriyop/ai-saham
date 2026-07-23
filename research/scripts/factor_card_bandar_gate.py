#!/usr/bin/env python3
"""Factor card: BandarGate false-positive dig (Package C1 follow-up).

Research only — authority NONE.

C1 flagged full-panel BandarGate blocks as looking "too good" vs OPEN.
This card stratifies BandarGate blocks by 5d accdist label, BCI, regime,
and high-score counterfactual — without changing risk_engine.yaml.

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_bandar_gate.py
  .venv/bin/python research/scripts/factor_card_bandar_gate.py \\
      --out research/artifacts/factor_card_bandar_gate_schema8.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lab.panel import PanelRow, load_swing10d_panel, resolve_db_path

ENTER_SCORE_FLOOR = 72.0
COVERAGE_FLOOR = 0.70
LEFT_TAIL_MAE = -8.0
DIST_LABELS = ("Small Dist", "Big Dist")
REGIME_ORDER = ("RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE", "UNKNOWN")
BCI_ORDER = ("CLUSTER", "STABLE", "RETAIL-LED", "UNKNOWN")


def _stats(rows: list[PanelRow]) -> dict[str, float | int | None]:
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "hit_pct": None,
            "avg_ret": None,
            "pf": None,
            "avg_mae": None,
            "left_tail_pct": None,
        }
    successes = sum(1 for r in rows if r.outcome_label == "SUCCESS")
    returns = [r.close_return for r in rows if r.close_return is not None]
    maes = [r.max_adverse_excursion for r in rows if r.max_adverse_excursion is not None]
    avg_ret = mean(returns) if returns else None
    avg_mae = mean(maes) if maes else None
    wins = [x for x in returns if x > 0]
    losses = [x for x in returns if x < 0]
    gross_loss = abs(sum(losses))
    pf = (sum(wins) / gross_loss) if gross_loss > 0 else None
    left_tail = (
        100.0 * sum(1 for m in maes if m <= LEFT_TAIL_MAE) / len(maes) if maes else None
    )
    return {
        "n": n,
        "hit_pct": 100.0 * successes / n,
        "avg_ret": avg_ret,
        "pf": pf,
        "avg_mae": avg_mae,
        "left_tail_pct": left_tail,
    }


def _fmt(stats: dict[str, float | int | None]) -> str:
    n = stats["n"]
    if not n:
        return "0 | — | — | — | — | —"
    hit = f"{stats['hit_pct']:.1f}" if stats["hit_pct"] is not None else "—"
    avg = f"{stats['avg_ret']:+.2f}" if stats["avg_ret"] is not None else "—"
    pf = f"{stats['pf']:.2f}" if stats["pf"] is not None else "—"
    mae = f"{stats['avg_mae']:+.2f}" if stats["avg_mae"] is not None else "—"
    tail = (
        f"{stats['left_tail_pct']:.1f}"
        if stats["left_tail_pct"] is not None
        else "—"
    )
    return f"{n} | {hit} | {avg} | {pf} | {mae} | {tail}"


def _table(title: str, cohorts: list[tuple[str, list[PanelRow]]]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        f"| Cohort | n | Hit % | Avg close ret % | PF | Avg MAE % | MAE≤{LEFT_TAIL_MAE:.0f}% % |",
        "|--------|---|-------|-----------------|----|-----------|--------------|",
    ]
    for name, rows in cohorts:
        lines.append(f"| {name} | {_fmt(_stats(rows))} |")
    lines.append("")
    return lines


def _norm_regime(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    text = str(value).strip().upper()
    return text if text else "UNKNOWN"


def _norm_bci(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    text = str(value).strip().upper()
    return text if text else "UNKNOWN"


def _is_bandar_blocked(row: PanelRow) -> bool:
    return (row.risk_gate or "") == "BandarGate"


def _is_open(row: PanelRow) -> bool:
    return (row.risk_status or "").upper() == "OPEN"


def _high_score(row: PanelRow) -> bool:
    if row.signal_score is None or row.signal_score < ENTER_SCORE_FLOOR:
        return False
    if (
        row.signal_authority_coverage is not None
        and row.signal_authority_coverage < COVERAGE_FLOOR
    ):
        return False
    return True


def _score_bucket(score: float | None) -> str:
    if score is None:
        return "score unknown"
    if score >= 90:
        return "90+"
    if score >= 80:
        return "80–89"
    if score >= ENTER_SCORE_FLOOR:
        return f"{ENTER_SCORE_FLOOR:.0f}–79"
    if score >= 45:
        return "45–71"
    return "<45"


def build_report(panel: list[PanelRow], db_path: Path) -> str:
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "—"
    open_rows = [r for r in panel if _is_open(r)]
    bandar = [r for r in panel if _is_bandar_blocked(r)]
    other_blocked = [
        r
        for r in panel
        if (r.risk_status or "").upper() == "BLOCKED" and not _is_bandar_blocked(r)
    ]

    baseline = [
        ("panel (all joinable)", panel),
        ("OPEN", open_rows),
        ("BandarGate BLOCKED", bandar),
        ("other BLOCKED (non-Bandar)", other_blocked),
    ]

    by_label: list[tuple[str, list[PanelRow]]] = []
    for label in DIST_LABELS:
        by_label.append(
            (
                f"BandarGate · {label}",
                [r for r in bandar if (r.five_day_accdist or "") == label],
            )
        )
    other_labels = [
        r
        for r in bandar
        if (r.five_day_accdist or "") not in DIST_LABELS
    ]
    if other_labels:
        by_label.append(("BandarGate · unexpected label/missing", other_labels))
    # OPEN with distribution labels should be rare (gate should have fired)
    for label in DIST_LABELS:
        by_label.append(
            (
                f"OPEN · five_day={label} (should be rare)",
                [
                    r
                    for r in open_rows
                    if (r.five_day_accdist or "") == label
                ],
            )
        )
    open_non_dist = [
        r
        for r in open_rows
        if (r.five_day_accdist or "") not in DIST_LABELS
    ]
    by_label.append(("OPEN · non-distribution / missing 5d", open_non_dist))

    bci_cohorts: list[tuple[str, list[PanelRow]]] = []
    for bci in BCI_ORDER:
        blocked_bci = [r for r in bandar if _norm_bci(r.bci_label) == bci]
        open_bci = [r for r in open_rows if _norm_bci(r.bci_label) == bci]
        if blocked_bci or open_bci:
            bci_cohorts.append((f"BandarGate · BCI={bci}", blocked_bci))
            bci_cohorts.append((f"OPEN · BCI={bci}", open_bci))

    regime_cohorts: list[tuple[str, list[PanelRow]]] = []
    for regime in REGIME_ORDER:
        in_reg = [r for r in panel if _norm_regime(r.regime) == regime]
        if not in_reg:
            continue
        regime_cohorts.append(
            (f"{regime} · BandarGate", [r for r in in_reg if _is_bandar_blocked(r)])
        )
        regime_cohorts.append(
            (f"{regime} · OPEN", [r for r in in_reg if _is_open(r)])
        )

    score_cohorts: list[tuple[str, list[PanelRow]]] = []
    buckets = (f"{ENTER_SCORE_FLOOR:.0f}–79", "80–89", "90+", "45–71", "<45", "score unknown")
    for bucket in buckets:
        blocked_b = [r for r in bandar if _score_bucket(r.signal_score) == bucket]
        open_b = [r for r in open_rows if _score_bucket(r.signal_score) == bucket]
        if blocked_b or open_b:
            score_cohorts.append((f"BandarGate · {bucket}", blocked_b))
            score_cohorts.append((f"OPEN · {bucket}", open_b))

    high_open = [r for r in open_rows if _high_score(r)]
    high_bandar = [r for r in bandar if _high_score(r)]
    counterfactual = [
        (
            f"OPEN & score≥{ENTER_SCORE_FLOOR:.0f} & cov≥{COVERAGE_FLOOR:.2f}",
            high_open,
        ),
        (
            f"BandarGate & score≥{ENTER_SCORE_FLOOR:.0f} & cov≥{COVERAGE_FLOOR:.2f}",
            high_bandar,
        ),
    ]

    # CLUSTER + distribution: classic FP hypothesis for accumulation screen
    cluster_fp = [
        (
            "BandarGate · CLUSTER · Small Dist",
            [
                r
                for r in bandar
                if _norm_bci(r.bci_label) == "CLUSTER"
                and (r.five_day_accdist or "") == "Small Dist"
            ],
        ),
        (
            "BandarGate · CLUSTER · Big Dist",
            [
                r
                for r in bandar
                if _norm_bci(r.bci_label) == "CLUSTER"
                and (r.five_day_accdist or "") == "Big Dist"
            ],
        ),
        (
            "OPEN · CLUSTER (control)",
            [r for r in open_rows if _norm_bci(r.bci_label) == "CLUSTER"],
        ),
    ]

    open_s = _stats(open_rows)
    bandar_s = _stats(bandar)
    high_open_s = _stats(high_open)
    high_bandar_s = _stats(high_bandar)

    def _delta(
        a: dict[str, float | int | None],
        b: dict[str, float | int | None],
        key: str,
    ) -> str:
        if a[key] is None or b[key] is None:
            return "—"
        return f"{float(b[key]) - float(a[key]):+.2f}"  # type: ignore[arg-type]

    lines: list[str] = [
        "# Factor Card — BandarGate Dig (Package C1 follow-up)",
        "**Authority: NONE**",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical obs ⋈ SWING_10D labels (N={len(panel)}; {date_span})",
        f"- BandarGate blocked rows: {len(bandar)}",
        "",
        "## Hypothesis",
        "",
        "1. Full-panel BandarGate outperformance vs OPEN is a mix artifact (WATCH/AVOID).",
        "2. **High-score BandarGate blocks should still underperform** enter-eligible OPEN.",
        "3. `Small Dist` and/or `CLUSTER + Dist` may be false-positive over-blocks.",
        "4. `Big Dist` should show worse left-tail than `Small Dist` if the gate is calibrated.",
        "",
        "## Interpretation guardrails",
        "",
        "- BandarGate reads **only** `five_day_accdist` ∈ {Small Dist, Big Dist}; not BCI.",
        "- BCI (`CLUSTER`/`STABLE`/`RETAIL-LED`) is an independent foreign-flow construct.",
        "- Raw-market labels only; do not edit `config/risk_engine.yaml` from this card.",
        "- Prefer high-score counterfactual + MAE over full-panel averages.",
        "",
    ]
    lines.extend(_table("Baseline — BandarGate vs OPEN / other blocks", baseline))
    lines.extend(_table("By five_day_accdist label", by_label))
    lines.extend(_table("BandarGate × BCI (vs OPEN same BCI)", bci_cohorts))
    lines.extend(_table("BandarGate × regime", regime_cohorts))
    lines.extend(_table("BandarGate × signal score bucket", score_cohorts))
    lines.extend(
        _table(
            f"High-score counterfactual (score≥{ENTER_SCORE_FLOOR:.0f}, "
            f"cov≥{COVERAGE_FLOOR:.2f})",
            counterfactual,
        )
    )
    lines.extend(_table("FP probe — CLUSTER × distribution", cluster_fp))

    lines.extend(
        [
            "## Readout (auto, non-authoritative)",
            "",
            f"- BandarGate − OPEN hitΔ (pp): "
            f"{_delta(open_s, bandar_s, 'hit_pct')}",
            f"- BandarGate − OPEN avg retΔ: "
            f"{_delta(open_s, bandar_s, 'avg_ret')}",
            f"- BandarGate − OPEN avg MAEΔ: "
            f"{_delta(open_s, bandar_s, 'avg_mae')} "
            "(positive MAEΔ ⇒ milder drawdowns on blocked — weaker capital-save case)",
            f"- High-score BandarGate − OPEN hitΔ (pp): "
            f"{_delta(high_open_s, high_bandar_s, 'hit_pct')}",
            f"- High-score BandarGate − OPEN retΔ: "
            f"{_delta(high_open_s, high_bandar_s, 'avg_ret')}",
            "",
            "## Proposed config / engineering action",
            "",
            "**None automatic.** Decision guide:",
            "- If high-score BandarGate underperforms high-score OPEN → **keep gate**;",
            "  full-panel 'Bandar looks good' is not a weaken signal.",
            "- If `Small Dist` / `CLUSTER+Small Dist` matches or beats OPEN while",
            "  `Big Dist` is clearly worse → consider narrowing `distribution_labels`",
            "  to Big Dist only (requires OOS + promotion lane).",
            "- If OPEN rows with Dist labels appear in non-trivial n → investigate",
            "  missing GateContext / skip path (ties to Package C2).",
            "- Next engineering: C2 per-gate missingness, or C3 regime overlay product decision.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--regime-cohort-id", default=None)
    args = parser.parse_args()
    db_path = resolve_db_path(args.db)
    panel = load_swing10d_panel(db_path, regime_cohort_id=args.regime_cohort_id)
    report = build_report(panel, db_path)
    out = args.out or (
        ROOT
        / "research"
        / "artifacts"
        / f"factor_card_bandar_gate_{date.today().isoformat()}.md"
    )
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
