#!/usr/bin/env python3
"""Factor card: Setup gate thresholds (Package B2).

Research only — authority NONE.

Setup MATCH / PARTIAL / failed-gate details are **not** persisted on canonical
observations. This card recomputes named-setup gate pass/fail from candidate
fields + `config/swing_setups.yaml`, then measures SWING_10D outcomes.

Primary focus: foreign-bounce (score / VWAP / RSI / trend / flow%).
Also reports coiled-spring and pullback-continuation synthetic match cohorts.
Smart-money uses optional `broker_daily_flow` recompute (same gap as A4).

Usage (from repo root):
  .venv/bin/python research/scripts/factor_card_setup_gates.py
  .venv/bin/python research/scripts/factor_card_setup_gates.py --skip-smart-money
"""

from __future__ import annotations

import argparse
import sqlite3
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

DEFAULT_SETUPS = ROOT / "config" / "swing_setups.yaml"
DEFAULT_ACCUM = ROOT / "config" / "accumulation_screener.yaml"


@dataclass(frozen=True)
class GateResult:
    label: str
    passed: bool


@dataclass(frozen=True)
class SetupEval:
    match: str  # MATCH | PARTIAL | NO_MATCH
    failed: tuple[str, ...]
    gates: tuple[GateResult, ...]


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


def _classify(gates: list[GateResult], partial_max: int) -> SetupEval:
    failed = tuple(g.label for g in gates if not g.passed)
    if not failed:
        match = "MATCH"
    elif len(failed) <= partial_max:
        match = "PARTIAL"
    else:
        match = "NO_MATCH"
    return SetupEval(match=match, failed=failed, gates=tuple(gates))


def _load_setups(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("setups") or {}


def _load_broker_lists(path: Path) -> tuple[frozenset[str], frozenset[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    bq = ((data.get("accumulation_screener") or {}).get("broker_quality")) or {}
    smart = frozenset(
        str(c).upper() for c in ((bq.get("smart_money") or {}).get("brokers") or [])
    )
    noise = frozenset(
        str(c).upper() for c in ((bq.get("noise") or {}).get("brokers") or [])
    )
    return smart, noise


def eval_foreign_bounce(row: PanelRow, gates_cfg: dict, partial_max: int) -> SetupEval:
    score_min = float(gates_cfg.get("min_foreign_flow_score", 58.3))
    vwap_min = float(gates_cfg.get("min_vwap_discount_pct", 3.0))
    trend_req = str(gates_cfg.get("required_trend", "SIDE")).upper()
    flow_min = float(gates_cfg.get("min_flow_ratio_pct", 5.0))
    rsi_max = float(gates_cfg.get("max_rsi", 60.0))
    gates = [
        GateResult(
            "foreign_flow_score",
            row.foreign_flow_score is not None
            and row.foreign_flow_score >= score_min,
        ),
        GateResult(
            "fvwap%",
            row.vwap_discount_pct is not None and row.vwap_discount_pct >= vwap_min,
        ),
        GateResult(
            "trend",
            row.trend is not None and row.trend.upper() == trend_req,
        ),
        GateResult(
            "flow_pct",
            row.avg_flow_ratio is not None and row.avg_flow_ratio >= flow_min,
        ),
        GateResult("RSI present", row.rsi is not None),
        GateResult(
            "RSI",
            row.rsi is not None and row.rsi <= rsi_max,
        ),
    ]
    return _classify(gates, partial_max)


def eval_coiled_spring(row: PanelRow, gates_cfg: dict, partial_max: int) -> SetupEval:
    score_min = float(gates_cfg.get("min_foreign_flow_score", 50.0))
    bb_max = float(gates_cfg.get("max_bb_width_pctile", 0.20))
    flow_min = float(gates_cfg.get("min_flow_ratio_pct", 3.0))
    rsi_max = float(gates_cfg.get("max_rsi", 65.0))
    gates = [
        GateResult(
            "foreign_flow_score",
            row.foreign_flow_score is not None
            and row.foreign_flow_score >= score_min,
        ),
        GateResult(
            "bb_width_pctile",
            row.bb_width_pctile is not None and row.bb_width_pctile <= bb_max,
        ),
        GateResult(
            "flow_pct",
            row.avg_flow_ratio is not None and row.avg_flow_ratio >= flow_min,
        ),
        GateResult("RSI present", row.rsi is not None),
        GateResult("RSI", row.rsi is not None and row.rsi <= rsi_max),
    ]
    return _classify(gates, partial_max)


def eval_pullback(row: PanelRow, gates_cfg: dict, partial_max: int) -> SetupEval:
    score_min = float(gates_cfg.get("min_foreign_flow_score", 45.8))
    trend_req = str(gates_cfg.get("required_trend", "UP")).upper()
    flow_min = float(gates_cfg.get("min_flow_ratio_pct", 2.0))
    rsi_min = float(gates_cfg.get("min_rsi", 40.0))
    rsi_max = float(gates_cfg.get("max_rsi", 65.0))
    vwap_min = float(gates_cfg.get("min_vwap_discount_pct", -2.0))
    gates = [
        GateResult(
            "foreign_flow_score",
            row.foreign_flow_score is not None
            and row.foreign_flow_score >= score_min,
        ),
        GateResult(
            "trend",
            row.trend is not None and row.trend.upper() == trend_req,
        ),
        GateResult(
            "flow_pct",
            row.avg_flow_ratio is not None and row.avg_flow_ratio >= flow_min,
        ),
        GateResult("RSI lower", row.rsi is not None and row.rsi >= rsi_min),
        GateResult("RSI upper", row.rsi is not None and row.rsi <= rsi_max),
        GateResult(
            "fvwap%",
            row.vwap_discount_pct is not None and row.vwap_discount_pct >= vwap_min,
        ),
    ]
    return _classify(gates, partial_max)


def _recompute_smart_noise(
    panel: list[PanelRow],
    db_path: Path,
    *,
    smart: frozenset[str],
    noise: frozenset[str],
) -> dict[tuple[str, str, int], tuple[float | None, float | None, float | None]]:
    """(ticker, date, window) -> (smart_share, noise_share, smart_flow)."""
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

    out: dict[tuple[str, str, int], tuple[float | None, float | None, float | None]] = {}
    for ticker, snap, window in keys:
        flows = by_ticker.get(ticker) or []
        dates = sorted({d for d, _, _ in flows if d <= snap})[-window:]
        if not dates:
            out[(ticker, snap, window)] = (None, None, None)
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
        out[(ticker, snap, window)] = (smart_share, noise_share, smart_flow)
    return out


def eval_smart_money(
    row: PanelRow,
    gates_cfg: dict,
    partial_max: int,
    *,
    smart_share: float | None,
    noise_share: float | None,
    smart_flow: float | None,
) -> SetupEval:
    score_min = float(gates_cfg.get("min_foreign_flow_score", 50.0))
    smart_min = float(gates_cfg.get("min_smart_share_pct", 30.0))
    noise_max = float(gates_cfg.get("max_noise_share_pct", 60.0))
    min_smart_flow = float(gates_cfg.get("min_smart_flow_idr", 0.0))
    reject_sell = bool(gates_cfg.get("reject_smart_net_selling", True))
    gates = [
        GateResult(
            "foreign_flow_score",
            row.foreign_flow_score is not None
            and row.foreign_flow_score >= score_min,
        ),
        GateResult(
            "smart_flow",
            smart_flow is not None and smart_flow >= min_smart_flow,
        ),
        GateResult(
            "smart_share_pct",
            smart_share is not None and smart_share >= smart_min,
        ),
        GateResult(
            "noise_share_pct",
            noise_share is not None and noise_share <= noise_max,
        ),
        GateResult(
            "smart_net_selling",
            (not reject_sell)
            or (smart_flow is not None and smart_flow >= 0),
        ),
    ]
    return _classify(gates, partial_max)


def build_report(
    panel: list[PanelRow],
    db_path: Path,
    setups: dict,
    *,
    skip_smart_money: bool,
    accum_config: Path,
) -> str:
    dates = sorted({r.snapshot_date for r in panel})
    date_span = f"{dates[0]} → {dates[-1]}" if dates else "n/a"

    fb_cfg = setups.get("foreign-bounce") or {}
    cs_cfg = setups.get("coiled-spring") or {}
    pb_cfg = setups.get("pullback-continuation") or {}
    sm_cfg = setups.get("smart-money-confirmed") or {}

    fb_gates = fb_cfg.get("gates") or {}
    cs_gates = cs_cfg.get("gates") or {}
    pb_gates = pb_cfg.get("gates") or {}
    sm_gates = sm_cfg.get("gates") or {}
    fb_partial = int(fb_cfg.get("partial_max_failed_gates", 2))
    cs_partial = int(cs_cfg.get("partial_max_failed_gates", 2))
    pb_partial = int(pb_cfg.get("partial_max_failed_gates", 2))
    sm_partial = int(sm_cfg.get("partial_max_failed_gates", 1))

    fb_evals = [eval_foreign_bounce(r, fb_gates, fb_partial) for r in panel]
    cs_evals = [eval_coiled_spring(r, cs_gates, cs_partial) for r in panel]
    pb_evals = [eval_pullback(r, pb_gates, pb_partial) for r in panel]

    lines: list[str] = [
        "# Factor Card — Setup Gate Thresholds (B2)",
        "",
        "**Authority: NONE** — research card only; not a production config change.",
        "",
        f"- Generated: {date.today().isoformat()}",
        f"- Database: `{db_path}`",
        f"- Panel: canonical obs ⋈ SWING_10D labels ({len(panel)} rows; {date_span})",
        f"- Gate source: `config/swing_setups.yaml` (recomputed; MATCH not persisted)",
        "",
        "## Hypothesis",
        "",
        "Prod named-setup gate thresholds (esp. foreign-bounce score/VWAP/RSI) "
        "should identify higher-quality SWING_10D cohorts when all gates MATCH. "
        "Threshold sweeps ask whether current cutoffs are too tight or too loose.",
        "",
        "## Data gaps",
        "",
        "- `setup_match` / `failed_gates` / `match_strength` are **not** in "
        "observation payloads — all MATCH/PARTIAL below are **synthetic**.",
        "- Screen capture often omits SetupEvidence; fingerprint "
        "`matched_setup_families` is sparse.",
        "- Smart-money shares require `broker_daily_flow` recompute (tracked subset).",
        "",
    ]

    # Coverage of gate inputs
    lines.extend(
        [
            "## Gate-input coverage",
            "",
            "| Field | n non-null |",
            "|-------|------------|",
            f"| foreign_flow_score | {sum(1 for r in panel if r.foreign_flow_score is not None)} |",
            f"| vwap_discount_pct | {sum(1 for r in panel if r.vwap_discount_pct is not None)} |",
            f"| rsi | {sum(1 for r in panel if r.rsi is not None)} |",
            f"| trend | {sum(1 for r in panel if r.trend is not None)} |",
            f"| avg_flow_ratio | {sum(1 for r in panel if r.avg_flow_ratio is not None)} |",
            f"| bb_width_pctile | {sum(1 for r in panel if r.bb_width_pctile is not None)} |",
            "",
        ]
    )

    # Synthetic match tables
    def _by_match(
        evals: list[SetupEval],
    ) -> dict[str, list[PanelRow]]:
        out: dict[str, list[PanelRow]] = defaultdict(list)
        for row, ev in zip(panel, evals):
            out[ev.match].append(row)
        return out

    fb_by = _by_match(fb_evals)
    cs_by = _by_match(cs_evals)
    pb_by = _by_match(pb_evals)

    lines.extend(
        _table(
            "Foreign-bounce synthetic match (prod thresholds)",
            [
                ("MATCH", fb_by.get("MATCH", [])),
                ("PARTIAL", fb_by.get("PARTIAL", [])),
                ("NO_MATCH", fb_by.get("NO_MATCH", [])),
                ("All panel", panel),
            ],
        )
    )
    lines.extend(
        _table(
            "Coiled-spring synthetic match (prod thresholds)",
            [
                ("MATCH", cs_by.get("MATCH", [])),
                ("PARTIAL", cs_by.get("PARTIAL", [])),
                ("NO_MATCH", cs_by.get("NO_MATCH", [])),
            ],
        )
    )
    lines.extend(
        _table(
            "Pullback-continuation synthetic match (prod thresholds)",
            [
                ("MATCH", pb_by.get("MATCH", [])),
                ("PARTIAL", pb_by.get("PARTIAL", [])),
                ("NO_MATCH", pb_by.get("NO_MATCH", [])),
            ],
        )
    )

    # Per-gate pass rates for foreign-bounce
    gate_pass: dict[str, list[PanelRow]] = defaultdict(list)
    gate_fail: dict[str, list[PanelRow]] = defaultdict(list)
    for row, ev in zip(panel, fb_evals):
        for g in ev.gates:
            if g.passed:
                gate_pass[g.label].append(row)
            else:
                gate_fail[g.label].append(row)

    lines.extend(
        [
            "## Foreign-bounce per-gate pass vs fail → outcomes",
            "",
            "| Gate | Pass n | Hit% | Avg% | Fail n | Hit% | Avg% | Δ hit pp |",
            "|------|--------|------|------|--------|------|------|----------|",
        ]
    )
    for label in ("foreign_flow_score", "fvwap%", "trend", "flow_pct", "RSI present", "RSI"):
        p = _stats(gate_pass[label])
        f = _stats(gate_fail[label])
        p_hit = f"{p['hit_pct']:.1f}" if p["hit_pct"] is not None else "—"
        f_hit = f"{f['hit_pct']:.1f}" if f["hit_pct"] is not None else "—"
        p_avg = f"{p['avg_ret']:+.2f}" if p["avg_ret"] is not None else "—"
        f_avg = f"{f['avg_ret']:+.2f}" if f["avg_ret"] is not None else "—"
        if p["hit_pct"] is not None and f["hit_pct"] is not None:
            delta = f"{p['hit_pct'] - f['hit_pct']:+.1f}"
        else:
            delta = "—"
        lines.append(
            f"| {label} | {p['n']} | {p_hit} | {p_avg} | "
            f"{f['n']} | {f_hit} | {f_avg} | {delta} |"
        )
    lines.append("")

    # Threshold sweeps — foreign-bounce focused
    lines.extend(
        [
            "## Foreign-bounce threshold sweeps",
            "",
            "Each row: **other gates at prod defaults**, only the swept gate changes. "
            "Cohort = synthetic MATCH under that variant.",
            "",
        ]
    )

    # Score sweep
    lines.extend(
        [
            "### Score gate (`min_foreign_flow_score`), others at prod",
            "",
            "| Threshold | MATCH n | Hit % | Avg % | PF |",
            "|-----------|---------|-------|-------|----|",
        ]
    )
    for thr in (45.0, 50.0, 55.0, 58.3, 65.0, 70.0):
        cfg = dict(fb_gates)
        cfg["min_foreign_flow_score"] = thr
        matched = [
            r
            for r in panel
            if eval_foreign_bounce(r, cfg, fb_partial).match == "MATCH"
        ]
        lines.append(f"| ≥ {thr:g} | {_fmt(_stats(matched))} |")
    lines.append("")

    # VWAP sweep
    lines.extend(
        [
            "### VWAP discount gate (`min_vwap_discount_pct`), others at prod",
            "",
            "| Threshold | MATCH n | Hit % | Avg % | PF |",
            "|-----------|---------|-------|-------|----|",
        ]
    )
    for thr in (0.0, 3.0, 5.0, 8.0, 10.0):
        cfg = dict(fb_gates)
        cfg["min_vwap_discount_pct"] = thr
        matched = [
            r
            for r in panel
            if eval_foreign_bounce(r, cfg, fb_partial).match == "MATCH"
        ]
        lines.append(f"| ≥ {thr:g}% | {_fmt(_stats(matched))} |")
    lines.append("")

    # RSI sweep
    lines.extend(
        [
            "### RSI gate (`max_rsi`), others at prod",
            "",
            "| Threshold | MATCH n | Hit % | Avg % | PF |",
            "|-----------|---------|-------|-------|----|",
        ]
    )
    for thr in (55.0, 60.0, 65.0, 70.0):
        cfg = dict(fb_gates)
        cfg["max_rsi"] = thr
        matched = [
            r
            for r in panel
            if eval_foreign_bounce(r, cfg, fb_partial).match == "MATCH"
        ]
        lines.append(f"| ≤ {thr:g} | {_fmt(_stats(matched))} |")
    lines.append("")

    # Flow % sweep
    lines.extend(
        [
            "### Flow % gate (`min_flow_ratio_pct`), others at prod",
            "",
            "| Threshold | MATCH n | Hit % | Avg % | PF |",
            "|-----------|---------|-------|-------|----|",
        ]
    )
    for thr in (0.0, 2.0, 3.0, 5.0, 7.0):
        cfg = dict(fb_gates)
        cfg["min_flow_ratio_pct"] = thr
        matched = [
            r
            for r in panel
            if eval_foreign_bounce(r, cfg, fb_partial).match == "MATCH"
        ]
        lines.append(f"| ≥ {thr:g}% | {_fmt(_stats(matched))} |")
    lines.append("")

    # Trend requirement on/off
    side = [r for r in panel if (r.trend or "").upper() == "SIDE"]
    lines.extend(
        _table(
            "Trend context (foreign-bounce requires SIDE)",
            [
                ("trend == SIDE", side),
                ("trend != SIDE", [r for r in panel if (r.trend or "").upper() != "SIDE"]),
            ],
        )
    )

    # Failed-gate count distribution for FB
    fail_buckets: dict[str, list[PanelRow]] = defaultdict(list)
    for row, ev in zip(panel, fb_evals):
        n_fail = len(ev.failed)
        if n_fail == 0:
            key = "0 fails (MATCH)"
        elif n_fail <= fb_partial:
            key = f"1–{fb_partial} fails (PARTIAL)"
        else:
            key = f">{fb_partial} fails (NO_MATCH)"
        fail_buckets[key].append(row)
    lines.extend(
        _table(
            "Foreign-bounce failed-gate count",
            [(k, fail_buckets[k]) for k in sorted(fail_buckets)],
        )
    )

    # Smart money optional
    if not skip_smart_money and sm_cfg.get("enabled", True):
        smart, noise = _load_broker_lists(accum_config)
        shares = _recompute_smart_noise(panel, db_path, smart=smart, noise=noise)
        sm_evals: list[SetupEval] = []
        for r in panel:
            key = (r.ticker.upper(), r.snapshot_date, int(r.window_days or 7))
            ss, ns, sf = shares.get(key, (None, None, None))
            sm_evals.append(
                eval_smart_money(
                    r,
                    sm_gates,
                    sm_partial,
                    smart_share=ss,
                    noise_share=ns,
                    smart_flow=sf,
                )
            )
        sm_by = _by_match(sm_evals)
        lines.extend(
            _table(
                "Smart-money-confirmed synthetic match (recomputed shares)",
                [
                    ("MATCH", sm_by.get("MATCH", [])),
                    ("PARTIAL", sm_by.get("PARTIAL", [])),
                    ("NO_MATCH", sm_by.get("NO_MATCH", [])),
                ],
            )
        )
        # Gate proxy already in A4; here show share gate alone vs MATCH
        share_pass = []
        share_fail = []
        smart_min = float(sm_gates.get("min_smart_share_pct", 30.0))
        noise_max = float(sm_gates.get("max_noise_share_pct", 60.0))
        for r in panel:
            key = (r.ticker.upper(), r.snapshot_date, int(r.window_days or 7))
            ss, ns, _ = shares.get(key, (None, None, None))
            if ss is None or ns is None:
                continue
            if ss >= smart_min and ns <= noise_max:
                share_pass.append(r)
            else:
                share_fail.append(r)
        lines.extend(
            _table(
                "Smart/noise share gates only (30/60)",
                [
                    ("Pass share gates", share_pass),
                    ("Fail share gates", share_fail),
                ],
            )
        )
    else:
        lines.extend(
            [
                "## Smart-money-confirmed",
                "",
                "_Skipped (`--skip-smart-money`) or disabled in config._",
                "",
            ]
        )

    lines.extend(
        [
            "## Interpretation guardrails",
            "",
            "- Synthetic MATCH ≠ live ENTER; DecisionPolicy + RiskEngine still apply.",
            "- Thin MATCH counts under strict gates are expected on this corpus.",
            "- Prefer regime-stratified follow-up (B6) before global threshold promotion.",
            "- Do not change `swing_setups.yaml` from this card alone.",
            "",
            "## Proposed config / engineering action",
            "",
            "**None automatic.** Candidate follow-ups (human review):",
            "- If FB MATCH cohort is empty/tiny, loosen one binding gate "
            "(often `flow_pct` or `fvwap%`) and re-run",
            "- Persist setup evaluation (`match`, `failed_gates`) on observations "
            "to avoid recompute drift",
            "- Next: **B6 DecisionPolicy regime floors**",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--setups", type=Path, default=DEFAULT_SETUPS)
    parser.add_argument("--accum-config", type=Path, default=DEFAULT_ACCUM)
    parser.add_argument(
        "--skip-smart-money",
        action="store_true",
        help="Skip smart-money share recompute section",
    )
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)
    panel = load_swing10d_panel(db_path)
    setups = _load_setups(args.setups)
    report = build_report(
        panel,
        db_path,
        setups,
        skip_smart_money=args.skip_smart_money,
        accum_config=args.accum_config,
    )

    out = args.out
    if out is None:
        out = (
            ROOT
            / "research"
            / "artifacts"
            / f"factor_card_setup_gates_{date.today().isoformat()}.md"
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
