#!/usr/bin/env python3
"""Factor card: Market Context Engine factors vs IHSG forward returns.

Package D — research only, authority NONE.

Evaluates whether MCE factor scores / regimes discriminate subsequent IHSG
returns. Optionally reports ticker SWING_10D hit rate by regime from the
canonical observation panel (DecisionPolicy relevance).

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_mce_factors.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from math import sqrt
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lab.mce_panel import MceDayRow, load_mce_regime_panel
from research.lab.panel import load_swing10d_panel, resolve_db_path

FACTOR_ORDER = (
    "vix",
    "eido",
    "usd_idr",
    "idx_trend",
    "idx_breadth",
    "foreign_flow",
    "commodity_composite",
)


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


def _ret_stats(returns: list[float]) -> dict[str, float | int | None]:
    """IHSG forward returns are stored as fractions (0.05 = +5%)."""
    n = len(returns)
    if n == 0:
        return {"n": 0, "avg_pct": None, "hit_pct": None}
    avg = mean(returns)
    hits = sum(1 for r in returns if r > 0)
    return {
        "n": n,
        "avg_pct": 100.0 * avg,
        "hit_pct": 100.0 * hits / n,
    }


def _fmt_ret(stats: dict[str, float | int | None]) -> str:
    n = stats["n"]
    if not n:
        return "| 0 | — | — |"
    avg = stats["avg_pct"]
    hit = stats["hit_pct"]
    avg_s = f"{avg:+.2f}" if avg is not None else "—"
    hit_s = f"{hit:.1f}" if hit is not None else "—"
    return f"| {n} | {avg_s} | {hit_s} |"


def _factor_map(row: MceDayRow) -> dict[str, float]:
    out: dict[str, float] = {}
    for f in row.factors:
        if f.enabled and f.score is not None:
            out[f.name] = f.score
    return out


def build_report(mce_panel: list[MceDayRow], db_path: Path) -> str:
    dates = [r.as_of_date for r in mce_panel]
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"
    with_10d = [r for r in mce_panel if r.forward_ihsg_return_10d is not None]
    with_5d = [r for r in mce_panel if r.forward_ihsg_return_5d is not None]

    lines: list[str] = [
        "# Factor Card — Market Context Engine Factors",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: `market_context_snapshots` ⋈ `regime_observations` "
        f"(IHSG forward returns)",
        f"- Days: {len(mce_panel)} snapshots; "
        f"{len(with_5d)} with 5d IHSG label; {len(with_10d)} with 10d label",
        f"- Date span: {date_span}",
        "- IHSG returns stored as fractions; displayed as percent points",
        "",
        "## Hypothesis",
        "",
        "Higher MCE factor scores and RISK_ON regimes should associate with "
        "better subsequent IHSG returns; RISK_OFF / VOLATILE should associate "
        "with weaker or negative forwards. Factor weights (VIX/EIDO-heavy) are "
        "design defaults until this card supports reweighting.",
        "",
        "## Regime → IHSG forward returns",
        "",
        "| Regime | horizon | n | Avg IHSG % | % days IHSG > 0 |",
        "|--------|---------|---|------------|-----------------|",
    ]

    by_regime: dict[str, list[MceDayRow]] = defaultdict(list)
    for row in mce_panel:
        by_regime[row.regime].append(row)

    for regime in sorted(by_regime):
        for horizon, attr in (("5d", "forward_ihsg_return_5d"), ("10d", "forward_ihsg_return_10d")):
            rets = [
                getattr(r, attr)
                for r in by_regime[regime]
                if getattr(r, attr) is not None
            ]
            lines.append(f"| {regime} | {horizon} {_fmt_ret(_ret_stats(rets))}")

    lines.extend(
        [
            "",
            "## Conviction terciles → IHSG 10d",
            "",
            "Split labeled days by conviction into low / mid / high terciles.",
            "",
            "| Tercile | n | Avg IHSG 10d % | % days > 0 |",
            "|---------|---|---------------|------------|",
        ]
    )

    labeled = sorted(with_10d, key=lambda r: r.conviction)
    if len(labeled) >= 9:
        n = len(labeled)
        cuts = [labeled[: n // 3], labeled[n // 3 : 2 * n // 3], labeled[2 * n // 3 :]]
        for name, chunk in zip(("low", "mid", "high"), cuts):
            rets = [r.forward_ihsg_return_10d for r in chunk if r.forward_ihsg_return_10d is not None]
            lines.append(f"| {name} {_fmt_ret(_ret_stats(rets))}")
    else:
        lines.append("| (insufficient labeled days for terciles) | — | — | — |")

    lines.extend(
        [
            "",
            "## Per-factor score vs IHSG 10d",
            "",
            "For each enabled factor with a score: Pearson corr(score, IHSG10d), "
            "and high-vs-low split at the median score.",
            "",
            "| Factor | n | corr | High-score avg % | Low-score avg % | Δ (high−low) |",
            "|--------|---|------|------------------|-----------------|--------------|",
        ]
    )

    names = [n for n in FACTOR_ORDER]
    extras = sorted(
        {
            f.name
            for row in mce_panel
            for f in row.factors
            if f.name not in FACTOR_ORDER
        }
    )
    names.extend(extras)

    for name in names:
        pairs: list[tuple[float, float]] = []
        for row in with_10d:
            fmap = _factor_map(row)
            if name not in fmap:
                continue
            pairs.append((fmap[name], row.forward_ihsg_return_10d or 0.0))
        if not pairs:
            # Check if factor exists but always disabled / missing score
            present = any(any(f.name == name for f in r.factors) for r in mce_panel)
            if present:
                lines.append(f"| {name} | 0 | — | — | — | — |")
            continue
        scores = [p[0] for p in pairs]
        rets = [p[1] for p in pairs]
        corr = _pearson(scores, rets)
        med = median(scores)
        high = [r for s, r in pairs if s >= med]
        low = [r for s, r in pairs if s < med]
        high_avg = 100.0 * mean(high) if high else None
        low_avg = 100.0 * mean(low) if low else None
        delta = (
            (high_avg - low_avg)
            if high_avg is not None and low_avg is not None
            else None
        )
        corr_s = f"{corr:+.3f}" if corr is not None else "—"
        high_s = f"{high_avg:+.2f}" if high_avg is not None else "—"
        low_s = f"{low_avg:+.2f}" if low_avg is not None else "—"
        delta_s = f"{delta:+.2f}" if delta is not None else "—"
        lines.append(
            f"| {name} | {len(pairs)} | {corr_s} | {high_s} | {low_s} | {delta_s} |"
        )

    # Ticker SUCCESS by regime (DecisionPolicy relevance)
    lines.extend(
        [
            "",
            "## Ticker SWING_10D by regime (DecisionPolicy relevance)",
            "",
            "Canonical `candidate_observations` joined to labels; regime from "
            "`regime_observations` on snapshot date.",
            "",
            "| Regime | n | Hit % (SUCCESS) | Avg ticker close ret % |",
            "|--------|---|-----------------|------------------------|",
        ]
    )
    try:
        ticker_panel = load_swing10d_panel(db_path)
        by_tr: dict[str, list] = defaultdict(list)
        for row in ticker_panel:
            by_tr[row.regime or "UNKNOWN"].append(row)
        for regime in sorted(by_tr):
            rows = by_tr[regime]
            n = len(rows)
            hit = 100.0 * sum(1 for r in rows if r.outcome_label == "SUCCESS") / n
            rets = [r.close_return for r in rows if r.close_return is not None]
            avg = mean(rets) if rets else None
            avg_s = f"{avg:+.2f}" if avg is not None else "—"
            lines.append(f"| {regime} | {n} | {hit:.1f} | {avg_s} |")
    except FileNotFoundError:
        lines.append("| (ticker panel unavailable) | — | — | — |")

    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- Daily market panel (~200 rows) — low statistical power.",
            "- IHSG forwards are market-level, not executable ticker P&L.",
            "- Factor scores are contemporaneous with the regime day; this is "
            "association, not a purged walk-forward OOS test.",
            "- Commodity composite is usually disabled — expect empty/zero rows.",
            "- Positive corr means higher factor score co-moves with higher "
            "subsequent IHSG; sign flips matter for VIX (often inverted risk).",
            "",
            "## Proposed config action",
            "",
            "**None automatic.** Candidate follow-ups (human review only):",
            "- reweight IDX-native factors (`idx_breadth`, `foreign_flow`) if they "
            "dominate predictive Δ",
            "- add regime hysteresis if regime→return table is noisy",
            "- do not edit `config/market_context_engine.yaml` from this card alone",
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
    mce_panel = load_mce_regime_panel(db_path)
    report = build_report(mce_panel, db_path)

    out = args.out
    if out is None:
        out = (
            ROOT
            / "research"
            / "artifacts"
            / f"factor_card_mce_factors_{date.today().isoformat()}.md"
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
