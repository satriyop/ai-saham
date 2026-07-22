#!/usr/bin/env python3
"""Factor card: Accum sector/group breadth bonus (Package A3).

Research only — authority NONE.

Prefer persisted `sector_breadth_pct` / `sector_breadth_bonus` from candidate
payloads (added to `AccumulationCandidate.to_dict()`). Fall back to
reconstruction from same-day panel peers + `config/idx_groups.yaml` for older
rows that lack those keys.

Also reports fingerprint `sc_sector_breadth` (sector-context peer return breadth)
as a related DIAG signal — different definition from the Accum bonus.

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_sector_breadth.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lab.panel import PanelRow, load_swing10d_panel, resolve_db_path

DEFAULT_THRESHOLD = 0.60
DEFAULT_MIN_TICKERS = 3
DEFAULT_BONUS_PTS = 10.0


def _load_ticker_to_group(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = data.get("groups") or {}
    mapping: dict[str, str] = {}
    for group_id, info in groups.items():
        if not isinstance(info, dict):
            continue
        for ticker in info.get("tickers") or []:
            mapping[str(ticker).upper()] = str(group_id)
    return mapping


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


def _reconstruct_bonus(
    panel: list[PanelRow],
    ticker_to_group: dict[str, str],
    *,
    threshold: float,
    min_tickers: int,
) -> dict[tuple[str, str], tuple[bool, float | None, str | None]]:
    """Return (ticker, snapshot_date) -> (bonus_eligible, breadth_pct, group_id)."""
    by_day: dict[str, list[PanelRow]] = defaultdict(list)
    for row in panel:
        by_day[row.snapshot_date].append(row)

    out: dict[tuple[str, str], tuple[bool, float | None, str | None]] = {}
    for day, rows in by_day.items():
        by_group: dict[str, list[PanelRow]] = defaultdict(list)
        unmapped: list[PanelRow] = []
        for row in rows:
            group = ticker_to_group.get(row.ticker.upper())
            if group is None:
                unmapped.append(row)
            else:
                by_group[group].append(row)

        for row in unmapped:
            out[(row.ticker, day)] = (False, None, None)

        for group, members in by_group.items():
            with_ratio = [m for m in members if m.net_buy_ratio is not None]
            if not with_ratio:
                for m in members:
                    out[(m.ticker, day)] = (False, None, group)
                continue
            positive = sum(1 for m in with_ratio if (m.net_buy_ratio or 0.0) > 0)
            breadth = positive / len(with_ratio)
            eligible = len(with_ratio) >= min_tickers and breadth >= threshold
            for m in members:
                out[(m.ticker, day)] = (eligible, breadth, group)
    return out


def _resolve_eligibility(
    panel: list[PanelRow],
    ticker_to_group: dict[str, str],
    *,
    threshold: float,
    min_tickers: int,
    bonus_pts: float,
) -> tuple[
    dict[tuple[str, str], tuple[bool, float | None, str | None, str]],
    int,
    int,
]:
    """Prefer persisted bonus/pct; fall back to reconstruction.

    Returns:
      map (ticker, date) -> (eligible, breadth_pct, group_id, source)
      n_persisted, n_reconstructed
    """
    recon = _reconstruct_bonus(
        panel, ticker_to_group, threshold=threshold, min_tickers=min_tickers
    )
    out: dict[tuple[str, str], tuple[bool, float | None, str | None, str]] = {}
    n_persisted = 0
    n_reconstructed = 0
    for row in panel:
        key = (row.ticker, row.snapshot_date)
        group = ticker_to_group.get(row.ticker.upper())
        bonus = row.sector_breadth_bonus
        pct = row.sector_breadth_pct
        # Persisted when key present in panel load (bonus may be 0.0; pct may be None).
        # Prefer when either field was loaded from payload (bonus not None after load,
        # or pct not None). Panel defaults both to None when absent.
        if bonus is not None or pct is not None:
            applied = float(bonus or 0.0)
            eligible = applied > 0.0
            # If only pct persisted with bonus 0, still treat as persisted evidence.
            if bonus is None and pct is not None:
                eligible = (
                    group is not None
                    and pct >= threshold
                    # cannot know peer count from pct alone; keep eligibility on pct only
                    # when threshold met — reconstruction still used for group/min peers
                )
            out[key] = (eligible, pct, group, "persisted")
            n_persisted += 1
        else:
            eligible, breadth, group_id = recon[key]
            out[key] = (eligible, breadth, group_id, "reconstructed")
            n_reconstructed += 1
    return out, n_persisted, n_reconstructed


def _load_sc_breadth(db_path: Path) -> dict[tuple[str, str], float | None]:
    """Optional DIAG: fingerprint sc_sector_breadth by (ticker, date)."""
    import json
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT c.ticker, c.snapshot_date, c.payload_json
            FROM candidate_observations c
            """
        ).fetchall()
    finally:
        conn.close()

    out: dict[tuple[str, str], float | None] = {}
    for ticker, snap, payload_json in rows:
        fp = (json.loads(payload_json).get("sub_signal_fingerprint") or {})
        value = fp.get("sc_sector_breadth")
        try:
            out[(ticker, str(snap)[:10])] = float(value) if value is not None else None
        except (TypeError, ValueError):
            out[(ticker, str(snap)[:10])] = None
    return out


def build_report(
    panel: list[PanelRow],
    db_path: Path,
    ticker_to_group: dict[str, str],
    *,
    threshold: float,
    min_tickers: int,
    bonus_pts: float,
) -> str:
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"
    resolved, n_persisted, n_reconstructed = _resolve_eligibility(
        panel,
        ticker_to_group,
        threshold=threshold,
        min_tickers=min_tickers,
        bonus_pts=bonus_pts,
    )

    eligible = [r for r in panel if resolved[(r.ticker, r.snapshot_date)][0]]
    ineligible = [r for r in panel if not resolved[(r.ticker, r.snapshot_date)][0]]
    mapped = [
        r
        for r in panel
        if resolved[(r.ticker, r.snapshot_date)][2] is not None
    ]
    unmapped = [
        r
        for r in panel
        if resolved[(r.ticker, r.snapshot_date)][2] is None
    ]

    breadth_vals = [
        resolved[(r.ticker, r.snapshot_date)][1]
        for r in mapped
        if resolved[(r.ticker, r.snapshot_date)][1] is not None
    ]

    lines: list[str] = [
        "# Factor Card — Sector/Group Breadth Bonus (A3)",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical obs ⋈ SWING_10D labels ({len(panel)} rows; {date_span})",
        f"- Group map: `config/idx_groups.yaml` ({len(ticker_to_group)} tickers)",
        f"- Eligibility: prefer persisted `sector_breadth_*`; reconstruct peers on "
        f"same `snapshot_date` when absent (n≥{min_tickers}, breadth≥{threshold:g}; "
        f"bonus_pts={bonus_pts:g})",
        f"- Source mix: persisted={n_persisted}, reconstructed={n_reconstructed}",
        "",
        "## Data gaps (important)",
        "",
        "- `AccumulationCandidate.to_dict()` now writes `sector_breadth_pct` / "
        "`sector_breadth_bonus`. **Existing corpus rows** still lack keys until "
        "re-screen / backfill — card falls back to reconstruction for those.",
        "- Reconstruction uses **same calendar day’s panel peers**, not the exact "
        "live screen result set (approximation).",
        "- `idx_groups` is conglomerate membership, not industry sector "
        "(name “sector_breadth” in Accum is historical).",
        "- Fingerprint `sc_sector` / `tp_sector` are null on this corpus; "
        "`sc_sector_breadth` is a **different** DIAG metric (peer 20d return breadth).",
        "",
        "## Hypothesis",
        "",
        "Tickers with applied / reconstructed bonus eligibility (group peers mostly "
        "net-buying) should show better SWING_10D outcomes if the Accum breadth bonus "
        "is information, not noise/dilution.",
        "",
        "## Coverage",
        "",
        "| Cohort | n |",
        "|--------|---|",
        f"| Mapped to idx_groups | {len(mapped)} |",
        f"| Unmapped (never bonus-eligible) | {len(unmapped)} |",
        f"| Bonus-eligible | {len(eligible)} |",
        f"| Not eligible | {len(ineligible)} |",
        f"| Eligibility from persisted fields | {n_persisted} |",
        f"| Eligibility reconstructed | {n_reconstructed} |",
        (
            f"| Breadth among mapped (median) | "
            f"{median(breadth_vals):.3f} |"
            if breadth_vals
            else "| Breadth among mapped (median) | — |"
        ),
        "",
        "## Bonus eligibility → outcomes",
        "",
        "| Cohort | n | Hit % | Avg close ret % | PF |",
        "|--------|---|-------|-----------------|----|",
        f"| Bonus-eligible | {_fmt(_stats(eligible))} |",
        f"| Not eligible | {_fmt(_stats(ineligible))} |",
        f"| Mapped only | {_fmt(_stats(mapped))} |",
        f"| Unmapped only | {_fmt(_stats(unmapped))} |",
        f"| All panel | {_fmt(_stats(panel))} |",
        "",
    ]

    # Breadth terciles among mapped
    lines.extend(
        [
            "## Breadth terciles (mapped only)",
            "",
            "| Tercile | n | Hit % | Avg % | PF |",
            "|---------|---|-------|-------|----|",
        ]
    )
    mapped_with_b = [
        (r, resolved[(r.ticker, r.snapshot_date)][1])
        for r in mapped
        if resolved[(r.ticker, r.snapshot_date)][1] is not None
    ]
    mapped_with_b.sort(key=lambda x: x[1] or 0.0)
    if len(mapped_with_b) >= 9:
        n = len(mapped_with_b)
        chunks = [
            mapped_with_b[: n // 3],
            mapped_with_b[n // 3 : 2 * n // 3],
            mapped_with_b[2 * n // 3 :],
        ]
        for name, chunk in zip(("low", "mid", "high"), chunks):
            lines.append(f"| {name} | {_fmt(_stats([r for r, _ in chunk]))} |")
    else:
        lines.append("| (insufficient mapped rows) | — | — | — | — |")

    # Score-without-bonus proxy among eligible
    lines.extend(
        [
            "",
            "## Score dilution proxy (eligible only)",
            "",
            f"If bonus was applied, `foreign_flow_score` already includes "
            f"+{bonus_pts:g}. Compare eligible rows' full score vs score−"
            f"{bonus_pts:g} median splits (heuristic).",
            "",
            "| Split | n | Hit % | Avg % | PF |",
            "|-------|---|-------|-------|----|",
        ]
    )
    if eligible:
        scores = [r.foreign_flow_score for r in eligible if r.foreign_flow_score is not None]
        if len(scores) >= 10:
            med = median(scores)
            high = [r for r in eligible if (r.foreign_flow_score or 0) >= med]
            low = [r for r in eligible if (r.foreign_flow_score or 0) < med]
            lines.append(f"| Eligible full-score high | {_fmt(_stats(high))} |")
            lines.append(f"| Eligible full-score low | {_fmt(_stats(low))} |")
            adj = []
            for r in eligible:
                if r.foreign_flow_score is None:
                    continue
                # Prefer exact persisted bonus when available
                pts = (
                    float(r.sector_breadth_bonus)
                    if r.sector_breadth_bonus is not None and r.sector_breadth_bonus > 0
                    else bonus_pts
                )
                adj.append((r, r.foreign_flow_score - pts))
            med_adj = median([s for _, s in adj])
            high_adj = [r for r, s in adj if s >= med_adj]
            low_adj = [r for r, s in adj if s < med_adj]
            lines.append(
                f"| Eligible score−bonus high | {_fmt(_stats(high_adj))} |"
            )
            lines.append(
                f"| Eligible score−bonus low | {_fmt(_stats(low_adj))} |"
            )
        else:
            lines.append("| (too few eligible) | — | — | — | — |")
    else:
        lines.append("| (no eligible rows) | — | — | — | — |")

    # DIAG sc_sector_breadth
    sc_map = _load_sc_breadth(db_path)
    sc_rows = []
    for r in panel:
        v = sc_map.get((r.ticker, r.snapshot_date))
        if v is not None:
            sc_rows.append((r, v))
    lines.extend(
        [
            "",
            "## Related DIAG: `sc_sector_breadth` (not Accum bonus)",
            "",
            "Peer **20d return** breadth from sector-context evidence. "
            "Threshold 0.60 mirrors Accum config only as a convenience split.",
            "",
            "| Cohort | n | Hit % | Avg % | PF |",
            "|--------|---|-------|-------|----|",
        ]
    )
    if sc_rows:
        high = [r for r, v in sc_rows if v >= threshold]
        low = [r for r, v in sc_rows if v < threshold]
        lines.append(f"| sc_breadth ≥ {threshold:g} | {_fmt(_stats(high))} |")
        lines.append(f"| sc_breadth < {threshold:g} | {_fmt(_stats(low))} |")
        lines.append(f"| sc_breadth present | {_fmt(_stats([r for r, _ in sc_rows]))} |")
    else:
        lines.append("| (no sc_sector_breadth values) | — | — | — | — |")

    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- Prefer persisted `sector_breadth_*` after re-screen; treat "
            "reconstructed results as provisional.",
            "- High unmapped share means most names never receive the live bonus.",
            "- Do not conflate conglomerate-group breadth with industry sector breadth.",
            "- Positive eligible−ineligible gap supports keeping the bonus; "
            "flat/negative supports disable or shrink `bonus_pts`.",
            "",
            "## Proposed config / engineering action",
            "",
            "**None automatic.** Candidate follow-ups (human review):",
            "- Re-screen / backfill so new observations carry `sector_breadth_*`",
            "- Optionally disable or lower `accumulation_screener.sector_breadth.bonus_pts` "
            "if eligible cohort does not outperform",
            "- Next Package A item: **A4 broker list quality**",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--groups",
        type=Path,
        default=ROOT / "config" / "idx_groups.yaml",
        help="Path to idx_groups.yaml",
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--min-tickers", type=int, default=DEFAULT_MIN_TICKERS)
    parser.add_argument("--bonus-pts", type=float, default=DEFAULT_BONUS_PTS)
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    panel = load_swing10d_panel(db_path)
    ticker_to_group = _load_ticker_to_group(args.groups)
    report = build_report(
        panel,
        db_path,
        ticker_to_group,
        threshold=args.threshold,
        min_tickers=args.min_tickers,
        bonus_pts=args.bonus_pts,
    )

    out = args.out
    if out is None:
        out = (
            ROOT
            / "research"
            / "artifacts"
            / f"factor_card_sector_breadth_{date.today().isoformat()}.md"
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
