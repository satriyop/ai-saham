#!/usr/bin/env python3
"""Factor card: DecisionPolicy regime floors (Package B6).

Research only — authority NONE.

Stratifies SWING_10D outcomes by market regime × signal score × realized
trade_setup.action / entry_quality, and compares against configured
`signal_engine.decision_policy.regime_policy` floors (enter / watch /
authority coverage).

Also runs a lightweight counterfactual: preliminary classification (70/45)
capped by regime floors using the **joined** `regime_observations.regime`
(not `decision_constraints.regime`, which is often null → defaults to RISK_ON
at capture).

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_regime_policy.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lab.panel import PanelRow, load_swing10d_panel, resolve_db_path

DEFAULT_SIGNAL_ENGINE = ROOT / "config" / "signal_engine.yaml"
STRONG_MIN = 70
MODERATE_MIN = 45
REGIME_ORDER = ("RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE", "UNKNOWN")


@dataclass(frozen=True)
class RegimeFloor:
    enter_allowed: bool
    enter_threshold: float | None
    watch_threshold: float
    min_signal_authority_coverage: float
    max_decision: str


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
    hit = f"{stats['hit_pct']:.1f}" if stats["hit_pct"] is not None else "—"
    avg = f"{stats['avg_ret']:+.2f}" if stats["avg_ret"] is not None else "—"
    pf = f"{stats['pf']:.2f}" if stats["pf"] is not None else "—"
    return f"{n} | {hit} | {avg} | {pf}"


def _table(title: str, cohorts: list[tuple[str, list[PanelRow]]]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Cohort | n | Hit % | Avg close ret % | PF |",
        "|--------|---|-------|-----------------|----|",
    ]
    for name, rows in cohorts:
        lines.append(f"| {name} | {_fmt(_stats(rows))} |")
    lines.append("")
    return lines


def _load_regime_floors(path: Path) -> dict[str, RegimeFloor]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    policy = (
        ((data.get("signal_engine") or {}).get("decision_policy") or {}).get(
            "regime_policy"
        )
        or {}
    )
    out: dict[str, RegimeFloor] = {}
    for regime, raw in policy.items():
        if not isinstance(raw, dict):
            continue
        enter_thr = raw.get("enter_threshold")
        out[str(regime).upper()] = RegimeFloor(
            enter_allowed=bool(raw.get("enter_allowed", False)),
            enter_threshold=float(enter_thr) if enter_thr is not None else None,
            watch_threshold=float(raw.get("watch_threshold", 45)),
            min_signal_authority_coverage=float(
                raw.get("min_signal_authority_coverage", 0.70)
            ),
            max_decision=str(raw.get("max_decision", "WATCH")).upper(),
        )
    return out


def _norm_regime(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    return str(value).strip().upper()


def _score_bucket(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score < 45:
        return "<45"
    if score < 70:
        return "45–69"
    if score < 72:
        return "70–71"
    if score < 80:
        return "72–79"
    return "80+"


def _coverage_bucket(cov: float | None) -> str:
    if cov is None:
        return "UNKNOWN"
    if cov < 0.40:
        return "LOW (<0.40)"
    if cov < 0.70:
        return "MED (0.40–0.69)"
    return "HIGH (≥0.70)"


def _order(decision: str) -> int:
    return {"AVOID": 0, "WATCH": 1, "ENTER": 2}.get(decision, 0)


def _stricter(a: str, b: str) -> str:
    return a if _order(a) <= _order(b) else b


def _preliminary(score: float | None, gate_tightening: bool | None) -> str:
    if score is None:
        return "AVOID"
    if score >= STRONG_MIN:
        quality = "ENTER"
    elif score >= MODERATE_MIN:
        quality = "WATCH"
    else:
        quality = "AVOID"
    if gate_tightening and quality == "ENTER":
        return "WATCH"
    return quality


def _apply_floors(
    preliminary: str,
    score: float | None,
    coverage: float | None,
    floor: RegimeFloor,
) -> str:
    """Mirror DecisionPolicy score + authority floors (no setup/readiness)."""
    max_decision = floor.max_decision
    if not floor.enter_allowed:
        max_decision = _stricter(max_decision, "WATCH")

    score_val = score if score is not None else 0.0
    cov_val = coverage if coverage is not None else 0.0

    if (
        floor.enter_allowed
        and preliminary == "ENTER"
        and floor.enter_threshold is not None
        and score_val < floor.enter_threshold
    ):
        max_decision = _stricter(max_decision, "WATCH")

    if preliminary in {"ENTER", "WATCH"} and score_val < floor.watch_threshold:
        max_decision = _stricter(max_decision, "AVOID")

    if floor.enter_allowed and preliminary == "ENTER":
        if cov_val < floor.min_signal_authority_coverage:
            max_decision = _stricter(max_decision, "WATCH")
    if not floor.enter_allowed and preliminary in {"ENTER", "WATCH"}:
        if cov_val < floor.min_signal_authority_coverage:
            max_decision = _stricter(max_decision, "AVOID")

    return _stricter(preliminary, max_decision)


def build_report(
    panel: list[PanelRow],
    db_path: Path,
    floors: dict[str, RegimeFloor],
) -> str:
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"

    lines: list[str] = [
        "# Factor Card — DecisionPolicy Regime Floors (B6)",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical obs ⋈ SWING_10D labels ({len(panel)} rows; {date_span})",
        f"- Floors from `config/signal_engine.yaml` → `decision_policy.regime_policy`",
        f"- Classification defaults: STRONG≥{STRONG_MIN}, MODERATE≥{MODERATE_MIN}",
        "",
        "## Hypothesis",
        "",
        "Regime-specific enter/watch/authority floors should separate better vs "
        "worse SWING_10D cohorts. If floors never bind (or always bind via "
        "coverage=0), the policy is not being tested on this corpus.",
        "",
        "## Configured floors",
        "",
        "| Regime | enter_allowed | enter≥ | watch≥ | auth≥ | max_decision |",
        "|--------|---------------|--------|--------|-------|--------------|",
    ]
    for regime in REGIME_ORDER:
        floor = floors.get(regime)
        if floor is None:
            continue
        enter = "—" if floor.enter_threshold is None else f"{floor.enter_threshold:g}"
        lines.append(
            f"| {regime} | {floor.enter_allowed} | {enter} | "
            f"{floor.watch_threshold:g} | {floor.min_signal_authority_coverage:.2f} | "
            f"{floor.max_decision} |"
        )
    lines.append("")

    # Coverage / corpus diagnostics
    n_score = sum(1 for r in panel if r.signal_score is not None)
    n_eq = sum(1 for r in panel if r.entry_quality is not None)
    n_act = sum(1 for r in panel if r.trade_setup_action is not None)
    n_cov = sum(1 for r in panel if r.signal_authority_coverage is not None)
    cov_zero = sum(
        1
        for r in panel
        if r.signal_authority_coverage is not None and r.signal_authority_coverage == 0.0
    )
    dc_null = sum(1 for r in panel if not r.decision_regime)
    join_vs_dc_mismatch = sum(
        1
        for r in panel
        if r.decision_regime
        and _norm_regime(r.regime) != _norm_regime(r.decision_regime)
    )

    lines.extend(
        [
            "## Data gaps (critical)",
            "",
            "| Check | n |",
            "|-------|---|",
            f"| signal_score present | {n_score} |",
            f"| entry_quality present | {n_eq} |",
            f"| trade_setup.action present | {n_act} |",
            f"| signal_authority_coverage present | {n_cov} |",
            f"| coverage == 0.0 | {cov_zero} |",
            f"| decision_constraints.regime null | {dc_null} |",
            f"| join regime ≠ decision regime (when both set) | {join_vs_dc_mismatch} |",
            "",
            "- When `decision_constraints.regime` is null, DecisionPolicy defaults "
            "to **RISK_ON** floors at capture — even on NEUTRAL/RISK_OFF market days.",
            "- coverage=0.0 blocks ENTER under every regime auth floor (≥0.70).",
            "",
        ]
    )

    # Regime × outcomes
    by_reg: dict[str, list[PanelRow]] = defaultdict(list)
    for r in panel:
        by_reg[_norm_regime(r.regime)].append(r)
    lines.extend(
        _table(
            "SWING_10D by joined market regime",
            [(k, by_reg[k]) for k in REGIME_ORDER if k in by_reg]
            + [(k, by_reg[k]) for k in sorted(by_reg) if k not in REGIME_ORDER],
        )
    )

    # Realized actions / entry quality
    by_action: dict[str, list[PanelRow]] = defaultdict(list)
    by_eq: dict[str, list[PanelRow]] = defaultdict(list)
    for r in panel:
        by_action[r.trade_setup_action or "UNKNOWN"].append(r)
        by_eq[r.entry_quality or "UNKNOWN"].append(r)
    action_order = (
        "ENTER",
        "WATCH",
        "AVOID",
        "BLOCKED_EXECUTION",
        "BLOCKED_STRUCTURAL",
        "UNKNOWN",
    )
    lines.extend(
        _table(
            "Realized trade_setup.action → outcomes",
            [(k, by_action[k]) for k in action_order if k in by_action]
            + [(k, by_action[k]) for k in sorted(by_action) if k not in action_order],
        )
    )
    lines.extend(
        _table(
            "Post-policy entry_quality → outcomes",
            [
                (k, by_eq[k])
                for k in ("ENTER", "WATCH", "AVOID", "UNKNOWN")
                if k in by_eq
            ],
        )
    )

    # Regime × score bucket
    lines.extend(
        [
            "## Regime × signal score bucket → outcomes",
            "",
            "| Regime | Score bucket | n | Hit % | Avg % | PF |",
            "|--------|--------------|---|-------|-------|----|",
        ]
    )
    for regime in REGIME_ORDER:
        rows = by_reg.get(regime) or []
        if not rows:
            continue
        buckets: dict[str, list[PanelRow]] = defaultdict(list)
        for r in rows:
            buckets[_score_bucket(r.signal_score)].append(r)
        for bucket in ("<45", "45–69", "70–71", "72–79", "80+", "UNKNOWN"):
            if bucket not in buckets:
                continue
            lines.append(f"| {regime} | {bucket} | {_fmt(_stats(buckets[bucket]))} |")
    lines.append("")

    # Regime × action
    lines.extend(
        [
            "## Regime × trade_setup.action → outcomes",
            "",
            "| Regime | Action | n | Hit % | Avg % | PF |",
            "|--------|--------|---|-------|-------|----|",
        ]
    )
    for regime in REGIME_ORDER:
        rows = by_reg.get(regime) or []
        if not rows:
            continue
        acts: dict[str, list[PanelRow]] = defaultdict(list)
        for r in rows:
            acts[r.trade_setup_action or "UNKNOWN"].append(r)
        for act in action_order:
            if act not in acts:
                continue
            lines.append(f"| {regime} | {act} | {_fmt(_stats(acts[act]))} |")
    lines.append("")

    # Floor binding audit using joined regime
    lines.extend(
        [
            "## Floor pass rates (joined regime × configured floors)",
            "",
            "| Regime | n | score≥enter | score≥watch | cov≥auth | realized ENTER | realized WATCH |",
            "|--------|---|-------------|-------------|----------|----------------|----------------|",
        ]
    )
    for regime in REGIME_ORDER:
        rows = by_reg.get(regime) or []
        floor = floors.get(regime)
        if not rows or floor is None:
            continue
        n = len(rows)
        if floor.enter_threshold is None:
            enter_pass = "—"
        else:
            enter_n = sum(
                1
                for r in rows
                if r.signal_score is not None
                and r.signal_score >= floor.enter_threshold
            )
            enter_pass = f"{enter_n} ({100.0 * enter_n / n:.1f}%)"
        watch_n = sum(
            1
            for r in rows
            if r.signal_score is not None and r.signal_score >= floor.watch_threshold
        )
        auth_n = sum(
            1
            for r in rows
            if r.signal_authority_coverage is not None
            and r.signal_authority_coverage >= floor.min_signal_authority_coverage
        )
        enter_act = sum(1 for r in rows if r.trade_setup_action == "ENTER")
        watch_act = sum(1 for r in rows if r.trade_setup_action == "WATCH")
        lines.append(
            f"| {regime} | {n} | {enter_pass} | "
            f"{watch_n} ({100.0 * watch_n / n:.1f}%) | "
            f"{auth_n} ({100.0 * auth_n / n:.1f}%) | "
            f"{enter_act} | {watch_act} |"
        )
    lines.append("")

    # Coverage buckets
    by_cov: dict[str, list[PanelRow]] = defaultdict(list)
    for r in panel:
        by_cov[_coverage_bucket(r.signal_authority_coverage)].append(r)
    lines.extend(
        _table(
            "Authority coverage buckets → outcomes",
            [
                (k, by_cov[k])
                for k in (
                    "LOW (<0.40)",
                    "MED (0.40–0.69)",
                    "HIGH (≥0.70)",
                    "UNKNOWN",
                )
                if k in by_cov
            ],
        )
    )

    # Counterfactual using joined regime floors
    synth: dict[str, list[PanelRow]] = defaultdict(list)
    for r in panel:
        regime = _norm_regime(r.regime)
        floor = floors.get(regime) or floors.get("RISK_ON")
        if floor is None:
            continue
        prelim = _preliminary(r.signal_score, r.gate_tightening)
        quality = _apply_floors(
            prelim, r.signal_score, r.signal_authority_coverage, floor
        )
        synth[quality].append(r)

    lines.extend(
        _table(
            "Counterfactual entry_quality (joined-regime floors + coverage)",
            [
                ("Synthetic ENTER", synth.get("ENTER", [])),
                ("Synthetic WATCH", synth.get("WATCH", [])),
                ("Synthetic AVOID", synth.get("AVOID", [])),
            ],
        )
    )

    # Alt sweeps: enter threshold (ignore coverage for sensitivity — optional)
    lines.extend(
        [
            "## Counterfactual sweeps (joined regime; **ignore coverage**)",
            "",
            "Isolates score floors. Coverage remains 0.0 on this corpus and would "
            "otherwise zero out ENTER under prod auth floors.",
            "",
            "### Enter threshold sweep (enter-allowed regimes only)",
            "",
            "| Alt enter≥ | Synthetic ENTER n | Hit % | Avg % | PF |",
            "|------------|-------------------|-------|-------|----|",
        ]
    )
    for alt in (65.0, 68.0, 70.0, 72.0, 75.0):
        matched: list[PanelRow] = []
        for r in panel:
            regime = _norm_regime(r.regime)
            floor = floors.get(regime)
            if floor is None or not floor.enter_allowed:
                continue
            if r.signal_score is None or r.signal_score < alt:
                continue
            prelim = _preliminary(r.signal_score, r.gate_tightening)
            if prelim != "ENTER":
                continue
            # ignore coverage; still respect enter_allowed + watch floor
            fake = RegimeFloor(
                enter_allowed=True,
                enter_threshold=alt,
                watch_threshold=floor.watch_threshold,
                min_signal_authority_coverage=0.0,
                max_decision=floor.max_decision,
            )
            if _apply_floors(prelim, r.signal_score, 1.0, fake) == "ENTER":
                matched.append(r)
        lines.append(f"| {alt:g} | {_fmt(_stats(matched))} |")
    lines.append("")

    lines.extend(
        [
            "### Authority floor sweep (prod enter thresholds; coverage forced)",
            "",
            "| Auth floor | Synthetic ENTER n | Hit % | Avg % | PF |",
            "|------------|-------------------|-------|-------|----|",
        ]
    )
    for auth in (0.0, 0.50, 0.70, 0.80, 1.00):
        matched = []
        for r in panel:
            regime = _norm_regime(r.regime)
            floor = floors.get(regime)
            if floor is None or not floor.enter_allowed:
                continue
            prelim = _preliminary(r.signal_score, r.gate_tightening)
            fake = RegimeFloor(
                enter_allowed=True,
                enter_threshold=floor.enter_threshold,
                watch_threshold=floor.watch_threshold,
                min_signal_authority_coverage=auth,
                max_decision=floor.max_decision,
            )
            # Use actual coverage for auth>0; for 0.0 floor any coverage passes
            if (
                _apply_floors(
                    prelim, r.signal_score, r.signal_authority_coverage, fake
                )
                == "ENTER"
            ):
                matched.append(r)
        lines.append(f"| ≥ {auth:.2f} | {_fmt(_stats(matched))} |")
    lines.append("")

    # High-score cohort detail
    high = [r for r in panel if r.signal_score is not None and r.signal_score >= 70]
    lines.extend(
        _table(
            "Score ≥ 70 cohort (would be STRONG / preliminary ENTER)",
            [
                ("All score≥70", high),
                (
                    "score≥70 & joined RISK_ON",
                    [r for r in high if _norm_regime(r.regime) == "RISK_ON"],
                ),
                (
                    "score≥70 & joined NEUTRAL",
                    [r for r in high if _norm_regime(r.regime) == "NEUTRAL"],
                ),
                (
                    "score≥70 & joined RISK_OFF",
                    [r for r in high if _norm_regime(r.regime) == "RISK_OFF"],
                ),
                (
                    "score≥70 & entry_quality=WATCH",
                    [r for r in high if r.entry_quality == "WATCH"],
                ),
                (
                    "score≥70 & entry_quality=AVOID",
                    [r for r in high if r.entry_quality == "AVOID"],
                ),
            ],
        )
    )

    lines.extend(
        [
            "## Interpretation guardrails",
            "",
            "- Realized ENTER rate can be zero even when scores clear enter floors "
            "if authority coverage is 0 or market_context was missing at capture.",
            "- `trade_setup.action` also includes RiskEngine BLOCKED_* — not pure "
            "DecisionPolicy.",
            "- Counterfactuals that ignore coverage are diagnostic only.",
            "- Do not edit `signal_engine.yaml` from this card alone.",
            "",
            "## Proposed config / engineering action",
            "",
            "**None automatic.** Candidate follow-ups (human review):",
            "- Fix observation capture so `market_context` / "
            "`decision_constraints.regime` and non-zero "
            "`signal_authority_coverage` are persisted",
            "- Re-run B6 after coverage is meaningful; then revisit NEUTRAL "
            "enter 72 vs RISK_ON 70",
            "- Next: persist risk gate outcomes for Package C, or canonical "
            "backfill for power",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_SIGNAL_ENGINE)
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    panel = load_swing10d_panel(db_path)
    floors = _load_regime_floors(args.config)
    report = build_report(panel, db_path, floors)

    out = args.out
    if out is None:
        out = (
            ROOT
            / "research"
            / "artifacts"
            / f"factor_card_regime_policy_{date.today().isoformat()}.md"
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
