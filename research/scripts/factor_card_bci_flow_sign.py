#!/usr/bin/env python3
"""Factor card: BCI label × aggregate flow sign vs SWING_10D outcomes.

Package A2 (Accum feeder) — research only, authority NONE.

Replicates the S6 spike hypothesis on the *canonical* observation panel:
CLUSTER scoring authority may be harmful when same-window aggregate foreign
flow (`total_net_value`) is negative.

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_bci_flow_sign.py
  .venv/bin/python research/scripts/factor_card_bci_flow_sign.py --db data/db/data.db
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

BCI_ORDER = ("CLUSTER", "STABLE", "RETAIL-LED", "NONE", "UNKNOWN")


def _normalize_bci(label: str | None) -> str:
    if not label:
        return "UNKNOWN"
    upper = str(label).strip().upper()
    if upper in {"CLUSTER", "STABLE"}:
        return upper
    if upper in {"RETAIL-LED", "RETAIL_LED", "RETAIL"}:
        return "RETAIL-LED"
    if upper in {"NONE", "N/A", "NA"}:
        return "NONE"
    return upper


def _flow_sign(net: float | None) -> str:
    if net is None:
        return "UNKNOWN"
    if net > 0:
        return "POS"
    if net < 0:
        return "NEG"
    return "FLAT"


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
        # close_return is already percent points.
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


def _bucket_key(row: PanelRow) -> tuple[str, str]:
    return _normalize_bci(row.bci_label), _flow_sign(row.total_net_value)


def build_report(panel: list[PanelRow], db_path: Path) -> str:
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"

    by_cell: dict[tuple[str, str], list[PanelRow]] = defaultdict(list)
    for row in panel:
        by_cell[_bucket_key(row)].append(row)

    bci_labels = [b for b in BCI_ORDER if any(k[0] == b for k in by_cell)]
    extra_bci = sorted({k[0] for k in by_cell if k[0] not in BCI_ORDER})
    bci_labels.extend(extra_bci)
    flow_labels = ["POS", "NEG", "FLAT", "UNKNOWN"]
    flow_labels = [f for f in flow_labels if any(k[1] == f for k in by_cell)]

    lines: list[str] = [
        "# Factor Card — BCI × Aggregate Flow Sign",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical `candidate_observations` ⋈ `signal_forward_labels` "
        f"(horizon=`SWING_10D`)",
        f"- Rows: {len(panel)}",
        f"- Snapshot span: {date_span}",
        "- Flow proxy: sign of `candidate.total_net_value` (same-window IDR net "
        "foreign value; not a separate direction field)",
        "- Related prior spike: `docs/research/s6_bci_authority_spike.md` "
        "(quarantine corpus; this card uses canonical joins)",
        "",
        "## Hypothesis",
        "",
        "BCI `CLUSTER` currently awards full institutional points regardless of "
        "aggregate flow sign. If CLUSTER + negative `total_net_value` underperforms "
        "CLUSTER + positive (and looks similar to non-CLUSTER + negative), then "
        "unconditional CLUSTER authority is not data-supported.",
        "",
        "## Cross-tab (BCI × flow sign)",
        "",
        "| BCI | Flow | n | Hit % (SUCCESS) | Avg close ret % | Profit factor |",
        "|-----|------|---|-----------------|-----------------|---------------|",
    ]

    for bci in bci_labels:
        for flow in flow_labels:
            lines.append(
                f"| {bci} | {flow} {_fmt(_stats(by_cell.get((bci, flow), [])))}"
            )

    # Contrast rows highlighted in S6
    cluster_pos = by_cell.get(("CLUSTER", "POS"), [])
    cluster_neg = by_cell.get(("CLUSTER", "NEG"), [])
    non_cluster_neg: list[PanelRow] = []
    for (bci, flow), rows in by_cell.items():
        if flow == "NEG" and bci != "CLUSTER":
            non_cluster_neg.extend(rows)

    lines.extend(
        [
            "",
            "## Contrast (S6-style)",
            "",
            "| Cohort | n | Hit % | Avg close ret % | Profit factor |",
            "|--------|---|-------|-----------------|---------------|",
            f"| CLUSTER + POS flow {_fmt(_stats(cluster_pos))}",
            f"| CLUSTER + NEG flow {_fmt(_stats(cluster_neg))}",
            f"| non-CLUSTER + NEG flow {_fmt(_stats(non_cluster_neg))}",
            f"| All rows {_fmt(_stats(panel))}",
            "",
            "## Regime-stratified CLUSTER",
            "",
            "Regime from `regime_observations` on snapshot date "
            "(missing → `UNKNOWN`).",
            "",
        ]
    )

    for flow_tag, cohort in (("POS", cluster_pos), ("NEG", cluster_neg)):
        lines.append(f"### CLUSTER + {flow_tag}")
        lines.append("")
        lines.append(
            "| Regime | n | Hit % | Avg close ret % | Profit factor |"
        )
        lines.append("|--------|---|-------|-----------------|---------------|")
        by_regime: dict[str, list[PanelRow]] = defaultdict(list)
        for r in cohort:
            by_regime[r.regime or "UNKNOWN"].append(r)
        for regime in sorted(by_regime):
            lines.append(f"| {regime} {_fmt(_stats(by_regime[regime]))}")
        lines.append("")

    lines.extend(
        [
            "## Interpretation guardrails",
            "",
            "- Canonical panel only; quarantine excluded.",
            "- Labels are raw-market, not net-executable.",
            "- Short snapshot span → hypothesis generation, not promotion proof.",
            "- `total_net_value` sign is a proxy for aggregate flow direction.",
            "- If CLUSTER+NEG ≈ non-CLUSTER+NEG and worse than CLUSTER+POS, "
            "propose conditional BCI scoring (require positive aggregate flow) "
            "— do not silently edit `config/accumulation_screener.yaml`.",
            "",
            "## Proposed config action",
            "",
            "**None automatic.** Candidate follow-up (human review only):",
            "- zero / down-weight `bci.cluster_points` when `total_net_value < 0`",
            "- or score via `bci_absorption_ratio` only as a diagnostic until OOS",
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
        help="Output markdown path (default: research/artifacts/factor_card_bci_*.md)",
    )
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
            / f"factor_card_bci_flow_sign_{date.today().isoformat()}.md"
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
