#!/usr/bin/env python3
"""Factor card: RiskEngine gates vs SWING_10D outcomes (Package C).

Research only — authority NONE.

C1 — Do blocked names underperform would-be entries?
     Compare OPEN vs BLOCKED (overall + per gate_triggered) on hit-rate,
     avg close return, profit factor, and left-tail MAE.

C2 — Fail-open vs fail-closed (diagnostic only today):
     Full proof needs per-gate missingness / GateContext completeness.
     This card only stamps the gap and reports risk_source coverage.

C3-lite — Regime × risk status:
     Stratify OPEN vs BLOCKED by joined regime_observations.regime.
     Full C3 (regime:* overlay on RiskEngine) is NOT in the accumulation
     capture path today — documented as engineering follow-up.

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_risk_gates.py
  .venv/bin/python research/scripts/factor_card_risk_gates.py \\
      --out research/artifacts/factor_card_risk_gates_schema8.md
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lab.panel import PanelRow, load_swing10d_panel, resolve_db_path

GATE_ORDER = (
    "FundamentalGate",
    "LiquidityGate",
    "FreeFloatGate",
    "BandarGate",
    "TechnicalGate",
)
REGIME_ORDER = ("RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE", "UNKNOWN")
ENTER_SCORE_FLOOR = 72.0
COVERAGE_FLOOR = 0.70
LEFT_TAIL_MAE = -8.0  # pct points; deep drawdown proxy


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


def _is_open(row: PanelRow) -> bool:
    return (row.risk_status or "").upper() == "OPEN"


def _is_blocked(row: PanelRow) -> bool:
    return (row.risk_status or "").upper() == "BLOCKED"


def _enter_eligible_open(row: PanelRow) -> bool:
    """OPEN rows that clear the NEUTRAL enter floor proxies (score + coverage)."""
    if not _is_open(row):
        return False
    if row.signal_score is None or row.signal_score < ENTER_SCORE_FLOOR:
        return False
    if (
        row.signal_authority_coverage is not None
        and row.signal_authority_coverage < COVERAGE_FLOOR
    ):
        return False
    return True


def build_report(panel: list[PanelRow], db_path: Path) -> str:
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "—"
    sources = Counter(r.risk_source or "missing" for r in panel)
    with_risk = sum(1 for r in panel if r.risk_status is not None)
    open_rows = [r for r in panel if _is_open(r)]
    blocked_rows = [r for r in panel if _is_blocked(r)]
    missing_risk = [r for r in panel if r.risk_status is None]

    gate_counts = Counter(
        r.risk_gate for r in blocked_rows if r.risk_gate
    )
    gate_cohorts: list[tuple[str, list[PanelRow]]] = [
        ("panel (all joinable)", panel),
        ("OPEN", open_rows),
        ("BLOCKED (any gate)", blocked_rows),
    ]
    for gate in GATE_ORDER:
        gate_rows = [r for r in blocked_rows if r.risk_gate == gate]
        if gate_rows or gate in gate_counts:
            gate_cohorts.append((f"BLOCKED · {gate}", gate_rows))
    other_gates = [
        r
        for r in blocked_rows
        if r.risk_gate and r.risk_gate not in GATE_ORDER
    ]
    if other_gates:
        gate_cohorts.append(("BLOCKED · other/regime*", other_gates))
    if missing_risk:
        gate_cohorts.append(("risk_status missing", missing_risk))

    structural = [r for r in blocked_rows if r.gate_is_structural is True]
    execution = [r for r in blocked_rows if r.gate_is_structural is False]
    tier_cohorts = [
        ("OPEN", open_rows),
        ("BLOCKED_STRUCTURAL (inferred)", structural),
        ("BLOCKED_EXECUTION (inferred)", execution),
        (
            "BLOCKED · structural unknown",
            [
                r
                for r in blocked_rows
                if r.gate_is_structural is None
            ],
        ),
    ]

    # High-score counterfactual: would-be ENTER pool vs same-score blocked
    high_open = [r for r in open_rows if _enter_eligible_open(r)]
    high_blocked = [
        r
        for r in blocked_rows
        if r.signal_score is not None
        and r.signal_score >= ENTER_SCORE_FLOOR
        and (
            r.signal_authority_coverage is None
            or r.signal_authority_coverage >= COVERAGE_FLOOR
        )
    ]
    counterfactual = [
        (f"OPEN & score≥{ENTER_SCORE_FLOOR:.0f} & cov≥{COVERAGE_FLOOR:.2f}", high_open),
        (
            f"BLOCKED & score≥{ENTER_SCORE_FLOOR:.0f} & cov≥{COVERAGE_FLOOR:.2f}",
            high_blocked,
        ),
    ]

    # Action × risk (TradeSetup)
    action_groups: dict[str, list[PanelRow]] = {}
    for r in panel:
        key = r.trade_setup_action or "NULL"
        action_groups.setdefault(key, []).append(r)
    action_order = [
        "ENTER",
        "WATCH",
        "AVOID",
        "BLOCKED_STRUCTURAL",
        "BLOCKED_EXECUTION",
    ]
    action_cohorts = [
        (a, action_groups.get(a, []))
        for a in action_order
        if a in action_groups
    ]
    for a, rows in sorted(action_groups.items()):
        if a not in action_order:
            action_cohorts.append((a, rows))

    # C3-lite: regime × risk status
    regime_cohorts: list[tuple[str, list[PanelRow]]] = []
    for regime in REGIME_ORDER:
        in_reg = [r for r in panel if _norm_regime(r.regime) == regime]
        if not in_reg:
            continue
        regime_cohorts.append((f"{regime} · all", in_reg))
        regime_cohorts.append(
            (f"{regime} · OPEN", [r for r in in_reg if _is_open(r)])
        )
        regime_cohorts.append(
            (f"{regime} · BLOCKED", [r for r in in_reg if _is_blocked(r)])
        )

    lines: list[str] = [
        "# Factor Card — RiskEngine Gates (Package C1 / C3-lite)",
        "**Authority: NONE**",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical obs ⋈ SWING_10D labels (N={len(panel)}; {date_span})",
        f"- Risk coverage: {with_risk}/{len(panel)} rows with risk_status",
        f"- Risk source mix: {dict(sources)}",
        "",
        "## Hypothesis",
        "",
        "1. **C1:** Names blocked by RiskEngine should show weaker SWING_10D outcomes",
        "   and/or worse left-tail MAE than OPEN names in the same discovery panel.",
        "2. **C1 counterfactual:** Among score≥72 & coverage≥0.70 candidates, blocked",
        "   names should underperform the OPEN enter-eligible pool (capital saved).",
        "3. **C3-lite:** OPEN vs BLOCKED edge may differ by market regime.",
        "",
        "## Interpretation guardrails",
        "",
        "- Raw-market labels only — not net-executable P&L.",
        "- Panel is discovery survivors with risk assessed; not a screen-rejected",
        "  control population (`contains_control_population=false`).",
        "- Accumulation capture does **not** apply `RiskEngine` regime overlay",
        "  (`regime:RISK_OFF`); C3 full proof needs that wiring.",
        "- C2 fail-open/fail-closed needs per-gate missingness + GateContext",
        "  completeness (not in `RiskAssessment.to_dict()` today).",
        "- Child table `observation_risk_assessments` preferred when present;",
        "  otherwise lean `candidate.risk_*` / `trade_setup` from parent payload.",
        "- Do not edit `config/risk_engine.yaml` from this card alone.",
        "",
    ]
    lines.extend(_table("C1 — OPEN vs BLOCKED (and per gate)", gate_cohorts))
    lines.extend(_table("C1 — Structural vs execution tier", tier_cohorts))
    lines.extend(
        _table(
            f"C1 — High-score counterfactual (score≥{ENTER_SCORE_FLOOR:.0f}, "
            f"cov≥{COVERAGE_FLOOR:.2f})",
            counterfactual,
        )
    )
    lines.extend(_table("C1 — TradeSetup.action cohorts", action_cohorts))
    lines.extend(_table("C3-lite — Regime × risk status", regime_cohorts))

    # Verdict helpers
    open_s = _stats(open_rows)
    blocked_s = _stats(blocked_rows)
    high_open_s = _stats(high_open)
    high_blocked_s = _stats(high_blocked)

    def _delta_hit(
        a: dict[str, float | int | None], b: dict[str, float | int | None]
    ) -> str:
        if a["hit_pct"] is None or b["hit_pct"] is None:
            return "—"
        return f"{float(b['hit_pct']) - float(a['hit_pct']):+.1f} pp"

    def _delta_ret(
        a: dict[str, float | int | None], b: dict[str, float | int | None]
    ) -> str:
        if a["avg_ret"] is None or b["avg_ret"] is None:
            return "—"
        return f"{float(b['avg_ret']) - float(a['avg_ret']):+.2f}"

    lines.extend(
        [
            "## Readout (auto, non-authoritative)",
            "",
            f"- BLOCKED − OPEN hitΔ: {_delta_hit(open_s, blocked_s)} "
            "(negative ⇒ blocked weaker hit-rate — supports C1)",
            f"- BLOCKED − OPEN avg retΔ: {_delta_ret(open_s, blocked_s)} "
            "(negative ⇒ blocked underperform on return — supports C1)",
            f"- High-score BLOCKED − OPEN hitΔ: "
            f"{_delta_hit(high_open_s, high_blocked_s)}",
            f"- High-score BLOCKED − OPEN retΔ: "
            f"{_delta_ret(high_open_s, high_blocked_s)}",
            "",
            "## C2 status — fail-open / fail-closed",
            "",
            "**Producer ready** (`observation_risk_assessments` schema_version ≥ 2).",
            "New captures persist `gate_evaluations[]` (pass / skipped / triggered /",
            "blocked_on_missing / not_evaluated) and `gate_context.missingness`.",
            "This panel is still mostly pre-v2 until re-backfill.",
            "",
            "To measure fail-open vs fail-closed:",
            "1. Re-backfill LQ45 (or target universe) with current capture path.",
            "2. Filter child rows `schema_version >= 2`.",
            "3. Compare OPEN rows with any `outcome=skipped` vs counterfactual",
            "   `blocked_on_missing` under `missing_data_action: block`.",
            "",
            "## C3 status — regime overlay on RiskEngine",
            "",
            "C3-lite above joins `regime_observations` only. Accumulation funnel uses",
            "`AssessRiskUseCase` without `RiskEngine._apply_regime_gate()`, so",
            "`gate_triggered` never equals `regime:RISK_OFF` on these rows.",
            "",
            "Engineering follow-up for full C3:",
            "1. Decide whether accumulation capture should apply market-context",
            "   gate tightening into risk (product decision + ADR if needed).",
            "2. If yes, persist `regime:*` blocks on the risk child and re-prove.",
            "",
            "## Proposed config / engineering action",
            "",
            "**None automatic.** Human review of C1 tables:",
            "- Prefer the **high-score counterfactual** (score≥72 & cov≥0.70) over the",
            "  full-panel OPEN vs BLOCKED average — the full panel mixes WATCH/AVOID.",
            "- If high-score BLOCKED underperforms high-score OPEN, keep gates;",
            "  tighten only with OOS + promotion lane.",
            "- If a specific gate (e.g. BandarGate on the full panel) shows similar or",
            "  better outcomes than OPEN, investigate false positives before weakening.",
            "- Prefer MAE / left-tail over hit-rate alone for risk value.",
            "- Next: re-backfill for C2 schema-v2 child coverage, then fail-open card.",
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
        help="Output markdown path (default: research/artifacts/factor_card_risk_gates_<date>.md)",
    )
    parser.add_argument(
        "--regime-cohort-id",
        default=None,
        help="Override regime semantic_compatibility_id ('' for legacy untagged)",
    )
    args = parser.parse_args()
    db_path = resolve_db_path(args.db)
    panel = load_swing10d_panel(db_path, regime_cohort_id=args.regime_cohort_id)
    report = build_report(panel, db_path)
    out = args.out or (
        ROOT / "research" / "artifacts" / f"factor_card_risk_gates_{date.today().isoformat()}.md"
    )
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
