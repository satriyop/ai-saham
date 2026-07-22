#!/usr/bin/env python3
"""Factor card: Broker list quality — Tier1 / smart / noise (Package A4).

Research only — authority NONE.

Proves whether configured broker-list membership is associated with SWING_10D
outcomes:

1. Panel-first (persisted): BCI / tier1 count / institutional_flag / top_brokers
   overlap with configured lists.
2. Optional recompute from `broker_daily_flow`: smart_share / noise_share using
   the same smart/noise sets as `config/accumulation_screener.yaml`
   (tracked-broker subset only; MS/DB/ML/XC may be empty in DB).

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_broker_lists.py
  .venv/bin/python research/scripts/factor_card_broker_lists.py --skip-recompute
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lab.panel import PanelRow, load_swing10d_panel, resolve_db_path

DEFAULT_CONFIG = ROOT / "config" / "accumulation_screener.yaml"
DEFAULT_SMART_SHARE_GATE = 30.0
DEFAULT_NOISE_SHARE_GATE = 60.0


def _load_broker_lists(path: Path) -> dict[str, frozenset[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    bq = ((data.get("accumulation_screener") or {}).get("broker_quality")) or {}

    def _codes(section: str) -> frozenset[str]:
        brokers = ((bq.get(section) or {}).get("brokers")) or []
        return frozenset(str(c).strip().upper() for c in brokers if str(c).strip())

    return {
        "tier1": _codes("tier1"),
        "smart": _codes("smart_money"),
        "noise": _codes("noise"),
    }


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


def _normalize_bci(label: str | None) -> str:
    if not label:
        return "UNKNOWN"
    upper = str(label).strip().upper()
    if upper in {"CLUSTER", "STABLE"}:
        return upper
    if upper in {"RETAIL-LED", "RETAIL_LED", "RETAIL"}:
        return "RETAIL-LED"
    return upper


def _tier1_bucket(count: int | None) -> str:
    if count is None:
        return "UNKNOWN"
    if count <= 0:
        return "0"
    if count <= 2:
        return "1-2"
    return "3+"


def _overlap(top: tuple[str, ...] | None, codes: frozenset[str]) -> bool:
    if not top:
        return False
    return any(c in codes for c in top)


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


def _recompute_smart_noise(
    panel: list[PanelRow],
    db_path: Path,
    *,
    smart: frozenset[str],
    noise: frozenset[str],
) -> dict[tuple[str, str, int], tuple[float | None, float | None, str]]:
    """Return (ticker, date, window) -> (smart_share, noise_share, label)."""
    keys = {
        (r.ticker.upper(), r.snapshot_date, int(r.window_days or 7)) for r in panel
    }
    if not keys:
        return {}

    tickers = sorted({t for t, _, _ in keys})
    min_date = min(d for _, d, _ in keys)
    max_date = max(d for _, d, _ in keys)

    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" for _ in tickers)
        rows = conn.execute(
            f"""
            SELECT ticker, date, broker_code, net_value
            FROM broker_daily_flow
            WHERE ticker IN ({placeholders})
              AND date <= ?
              AND date >= date(?, '-180 days')
            ORDER BY ticker, date
            """,
            [*tickers, max_date, min_date],
        ).fetchall()
    finally:
        conn.close()

    by_ticker: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for ticker, flow_date, code, net_value in rows:
        try:
            net = float(net_value)
        except (TypeError, ValueError):
            continue
        by_ticker[str(ticker).upper()].append(
            (str(flow_date)[:10], str(code).upper(), net)
        )

    out: dict[tuple[str, str, int], tuple[float | None, float | None, str]] = {}
    for ticker, snap, window in keys:
        flows = by_ticker.get(ticker) or []
        dates = sorted({d for d, _, _ in flows if d <= snap})[-window:]
        if not dates:
            out[(ticker, snap, window)] = (None, None, "n/a")
            continue
        date_set = set(dates)
        smart_flow = 0.0
        noise_flow = 0.0
        neutral_flow = 0.0
        for d, code, net in flows:
            if d not in date_set:
                continue
            if code in smart:
                smart_flow += net
            elif code in noise:
                noise_flow += net
            else:
                neutral_flow += net
        total = abs(smart_flow) + abs(noise_flow) + abs(neutral_flow)
        smart_share = (100.0 * abs(smart_flow) / total) if total > 0 else None
        noise_share = (100.0 * abs(noise_flow) / total) if total > 0 else None
        if smart_flow < 0 and abs(smart_flow) >= abs(noise_flow):
            label = "smart-"
        elif noise_flow < 0 and abs(noise_flow) > abs(smart_flow):
            label = "noise-"
        elif smart_flow > 0 and smart_flow >= noise_flow and smart_flow >= neutral_flow:
            label = "smart+"
        elif noise_flow > 0 and noise_flow >= smart_flow and noise_flow >= neutral_flow:
            label = "noise+"
        elif neutral_flow != 0:
            label = "mixed"
        else:
            label = "n/a"
        out[(ticker, snap, window)] = (smart_share, noise_share, label)
    return out


def _broker_db_coverage(
    db_path: Path, lists: dict[str, frozenset[str]]
) -> dict[str, int]:
    all_codes = sorted(lists["tier1"] | lists["smart"] | lists["noise"])
    conn = sqlite3.connect(db_path)
    try:
        return {
            code: conn.execute(
                "SELECT COUNT(*) FROM broker_daily_flow WHERE broker_code = ?",
                (code,),
            ).fetchone()[0]
            for code in all_codes
        }
    finally:
        conn.close()


def _per_code_rows(
    panel: list[PanelRow],
    lists: dict[str, frozenset[str]],
) -> list[str]:
    tier1, smart, noise = lists["tier1"], lists["smart"], lists["noise"]
    all_list_codes = sorted(tier1 | smart | noise)
    lines = [
        "## Per-code: in top_brokers vs absent (configured lists only)",
        "",
        "Membership sensitivity proxy: when the code appears among Accum "
        "`top_brokers`, do SWING_10D outcomes look better?",
        "",
        "| Code | Lists | Present n | Hit% | Avg% | Absent n | Hit% | Avg% | Δ hit pp |",
        "|------|-------|-----------|------|------|----------|------|------|----------|",
    ]
    for code in all_list_codes:
        tags = []
        if code in tier1:
            tags.append("T1")
        if code in smart:
            tags.append("smart")
        if code in noise:
            tags.append("noise")
        present = [
            r for r in panel if r.top_brokers is not None and code in r.top_brokers
        ]
        absent = [
            r
            for r in panel
            if r.top_brokers is not None and code not in r.top_brokers
        ]
        sp = _stats(present)
        sa = _stats(absent)
        p_hit = f"{sp['hit_pct']:.1f}" if sp["hit_pct"] is not None else "—"
        a_hit = f"{sa['hit_pct']:.1f}" if sa["hit_pct"] is not None else "—"
        p_avg = f"{sp['avg_ret']:+.2f}" if sp["avg_ret"] is not None else "—"
        a_avg = f"{sa['avg_ret']:+.2f}" if sa["avg_ret"] is not None else "—"
        if sp["hit_pct"] is not None and sa["hit_pct"] is not None:
            delta = f"{sp['hit_pct'] - sa['hit_pct']:+.1f}"
        else:
            delta = "—"
        lines.append(
            f"| {code} | {','.join(tags)} | {sp['n']} | {p_hit} | {p_avg} | "
            f"{sa['n']} | {a_hit} | {a_avg} | {delta} |"
        )
    lines.append("")
    return lines


def build_report(
    panel: list[PanelRow],
    db_path: Path,
    lists: dict[str, frozenset[str]],
    *,
    skip_recompute: bool,
    smart_gate: float,
    noise_gate: float,
) -> str:
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"
    tier1 = lists["tier1"]
    smart = lists["smart"]
    noise = lists["noise"]
    all_list_codes = sorted(tier1 | smart | noise)

    has_top = sum(1 for r in panel if r.top_brokers is not None)
    has_bci = sum(1 for r in panel if r.bci_label is not None)
    has_count = sum(1 for r in panel if r.bci_tier1_count is not None)

    lines: list[str] = [
        "# Factor Card — Broker List Quality (A4)",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical obs ⋈ SWING_10D labels ({len(panel)} rows; {date_span})",
        f"- Lists from `config/accumulation_screener.yaml` → `broker_quality`",
        f"- Tier1 ({len(tier1)}): {', '.join(sorted(tier1))}",
        f"- Smart ({len(smart)}): {', '.join(sorted(smart))}",
        f"- Noise ({len(noise)}): {', '.join(sorted(noise))}",
        "",
        "## Hypothesis",
        "",
        "Configured Tier1 / smart / noise membership should separate SWING_10D "
        "outcomes if the lists encode real flow quality rather than folklore.",
        "",
        "## Coverage",
        "",
        "| Field | n with value |",
        "|-------|--------------|",
        f"| `bci_label` | {has_bci} |",
        f"| `bci_tier1_count` | {has_count} |",
        f"| `top_brokers` | {has_top} |",
        f"| All panel | {len(panel)} |",
        "",
        "## Data gaps",
        "",
        "- `smart_share_pct` / `noise_share_pct` are **not** in candidate payloads; "
        "optional section recomputes from tracked `broker_daily_flow` only.",
        "- `top_brokers` comes from Accum evaluator net buyers (tracked daily flow), "
        "not full-market `broker_summaries`.",
        "- Panel includes windows 7/30/90 (same as other A cards).",
        "",
    ]

    by_bci: dict[str, list[PanelRow]] = defaultdict(list)
    for r in panel:
        by_bci[_normalize_bci(r.bci_label)].append(r)
    bci_order = ["CLUSTER", "STABLE", "RETAIL-LED", "UNKNOWN"]
    lines.extend(
        _table(
            "BCI label (Tier1 count → label) → outcomes",
            [(k, by_bci[k]) for k in bci_order if k in by_bci]
            + [(k, by_bci[k]) for k in sorted(by_bci) if k not in bci_order],
        )
    )

    by_count: dict[str, list[PanelRow]] = defaultdict(list)
    for r in panel:
        by_count[_tier1_bucket(r.bci_tier1_count)].append(r)
    lines.extend(
        _table(
            "Tier1 count buckets → outcomes",
            [(k, by_count[k]) for k in ("0", "1-2", "3+", "UNKNOWN") if k in by_count],
        )
    )

    lines.extend(
        _table(
            "institutional_flag → outcomes",
            [
                (
                    "True (any Tier1 net buyer)",
                    [r for r in panel if r.institutional_flag is True],
                ),
                ("False", [r for r in panel if r.institutional_flag is False]),
                ("Unknown", [r for r in panel if r.institutional_flag is None]),
            ],
        )
    )

    lines.extend(
        _table(
            "top_brokers ∩ configured lists",
            [
                (
                    "Any Tier1 in top_brokers",
                    [r for r in panel if _overlap(r.top_brokers, tier1)],
                ),
                (
                    "No Tier1 in top_brokers",
                    [
                        r
                        for r in panel
                        if r.top_brokers is not None
                        and not _overlap(r.top_brokers, tier1)
                    ],
                ),
                (
                    "Any smart in top_brokers",
                    [r for r in panel if _overlap(r.top_brokers, smart)],
                ),
                (
                    "No smart in top_brokers",
                    [
                        r
                        for r in panel
                        if r.top_brokers is not None
                        and not _overlap(r.top_brokers, smart)
                    ],
                ),
                (
                    "Any noise in top_brokers",
                    [r for r in panel if _overlap(r.top_brokers, noise)],
                ),
                (
                    "No noise in top_brokers",
                    [
                        r
                        for r in panel
                        if r.top_brokers is not None
                        and not _overlap(r.top_brokers, noise)
                    ],
                ),
            ],
        )
    )

    lines.extend(_per_code_rows(panel, lists))

    db_counts = _broker_db_coverage(db_path, lists)
    lines.extend(
        [
            "## `broker_daily_flow` coverage for configured codes",
            "",
            "| Code | Lists | Rows in DB |",
            "|------|-------|------------|",
        ]
    )
    for code in all_list_codes:
        tags = []
        if code in tier1:
            tags.append("T1")
        if code in smart:
            tags.append("smart")
        if code in noise:
            tags.append("noise")
        lines.append(f"| {code} | {','.join(tags)} | {db_counts.get(code, 0)} |")
    missing = [c for c in all_list_codes if db_counts.get(c, 0) == 0]
    lines.append("")
    lines.append(
        "- Codes with **zero** daily-flow rows: "
        + (", ".join(missing) if missing else "(none)")
    )
    lines.append("")

    if not skip_recompute:
        recomputed = _recompute_smart_noise(panel, db_path, smart=smart, noise=noise)
        with_share = []
        for r in panel:
            key = (r.ticker.upper(), r.snapshot_date, int(r.window_days or 7))
            smart_share, noise_share, label = recomputed.get(
                key, (None, None, "n/a")
            )
            with_share.append((r, smart_share, noise_share, label))
        present_n = sum(1 for _, s, _, _ in with_share if s is not None)
        lines.extend(
            [
                "## Recomputed smart/noise share (tracked daily flow)",
                "",
                f"Window = candidate `window_days` (default 7). "
                f"Rows with share: {present_n}/{len(panel)}.",
                "",
                f"Gate mirrors (prod smart-money-confirmed): "
                f"smart_share≥{smart_gate:g}%, noise_share≤{noise_gate:g}%.",
                "",
            ]
        )
        by_label: dict[str, list[PanelRow]] = defaultdict(list)
        for r, _, _, label in with_share:
            by_label[label].append(r)
        label_order = ["smart+", "noise+", "smart-", "noise-", "mixed", "n/a"]
        lines.extend(
            _table(
                "Tracked quality label → outcomes",
                [(k, by_label[k]) for k in label_order if k in by_label]
                + [
                    (k, by_label[k])
                    for k in sorted(by_label)
                    if k not in label_order
                ],
            )
        )
        gate_pass = [
            r
            for r, s, n, _ in with_share
            if s is not None
            and n is not None
            and s >= smart_gate
            and n <= noise_gate
        ]
        gate_fail = [
            r
            for r, s, n, _ in with_share
            if s is not None
            and n is not None
            and not (s >= smart_gate and n <= noise_gate)
        ]
        no_share = [r for r, s, _, _ in with_share if s is None]
        lines.extend(
            _table(
                "Smart-money gate proxy (recomputed shares)",
                [
                    (
                        f"Pass (smart≥{smart_gate:g} & noise≤{noise_gate:g})",
                        gate_pass,
                    ),
                    ("Fail share gates", gate_fail),
                    ("No share (no daily flow in window)", no_share),
                ],
            )
        )
        share_rows = [(r, s) for r, s, _, _ in with_share if s is not None]
        share_rows.sort(key=lambda x: x[1] or 0.0)
        lines.extend(
            [
                "## Smart share terciles (recomputed)",
                "",
                "| Tercile | n | Hit % | Avg % | PF |",
                "|---------|---|-------|-------|----|",
            ]
        )
        if len(share_rows) >= 9:
            n = len(share_rows)
            chunks = [
                share_rows[: n // 3],
                share_rows[n // 3 : 2 * n // 3],
                share_rows[2 * n // 3 :],
            ]
            for name, chunk in zip(("low", "mid", "high"), chunks):
                lines.append(f"| {name} | {_fmt(_stats([r for r, _ in chunk]))} |")
        else:
            lines.append("| (insufficient rows) | — | — | — | — |")
        lines.append("")
    else:
        lines.extend(
            [
                "## Recomputed smart/noise share",
                "",
                "_Skipped (`--skip-recompute`)._",
                "",
            ]
        )

    lines.extend(
        [
            "## Interpretation guardrails",
            "",
            "- Tier1/BCI results partly overlap Package A2; read as list-membership "
            "evidence, not a new BCI authority claim.",
            "- Smart/noise recompute is tracked-subset only; missing codes weaken "
            "list validation.",
            "- `top_brokers` presence ≠ large IDR size — headcount bias remains.",
            "- Do not change `broker_quality` YAML from this card alone.",
            "",
            "## Proposed config / engineering action",
            "",
            "**None automatic.** Candidate follow-ups (human review):",
            "- Drop or demote codes that never appear / never have daily-flow rows",
            "- Persist `smart_share_pct` / `noise_share_pct` (or tracked label) on "
            "observations if smart-money gates stay in scope",
            "- Next after Package A: **B2/B6** setup gates & regime floors, or "
            "canonical backfill for exact A3 breadth fields",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to accumulation_screener.yaml",
    )
    parser.add_argument(
        "--skip-recompute",
        action="store_true",
        help="Skip broker_daily_flow smart/noise share recompute",
    )
    parser.add_argument("--smart-gate", type=float, default=DEFAULT_SMART_SHARE_GATE)
    parser.add_argument("--noise-gate", type=float, default=DEFAULT_NOISE_SHARE_GATE)
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    panel = load_swing10d_panel(db_path)
    lists = _load_broker_lists(args.config)
    report = build_report(
        panel,
        db_path,
        lists,
        skip_recompute=args.skip_recompute,
        smart_gate=args.smart_gate,
        noise_gate=args.noise_gate,
    )

    out = args.out
    if out is None:
        out = (
            ROOT
            / "research"
            / "artifacts"
            / f"factor_card_broker_lists_{date.today().isoformat()}.md"
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
