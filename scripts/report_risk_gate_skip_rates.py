#!/usr/bin/env python3
"""Report per-gate RiskEngine outcome rates from captured accum observations.

Measurement companion for the "unevaluable risk gate" work. It reads the
persisted `gate_evaluations` audit block out of `learning_observations` and
tallies each gate's outcome so the skip rate can be compared before and after
a change (or before and after a fundamentals backfill).

Read-only: opens SQLite in read-only mode and never writes.

Usage:
    python scripts/report_risk_gate_skip_rates.py [--db data/db/data.db]
                                                  [--window 7]
                                                  [--purpose ACCUMULATION_DISCOVERY]
                                                  [--format text|json]

Recorded baseline (2026-08-04, data/db/data.db, `--window all`,
7,764 accum window-observations):

    gate             pass  triggered  skipped  not_evaluated  unknown%
    BandarGate       2928       1545     1437           1854     18.5%
    FreeFloatGate    3630        588     2280           1266     29.4%
    FundamentalGate  3348        117     4299              0     55.4%
    LiquidityGate    6498       1149        0            117      0.0%

Layer: standalone operator script (not imported by src/).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

_OUTCOME_ORDER = (
    "pass",
    "triggered",
    "skipped",
    "unevaluable",
    "blocked_on_missing",
    "not_evaluated",
)


def _iter_gate_rows(db_path: Path, purpose: str, window: str):
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            "SELECT artifact_json FROM learning_observations WHERE purpose=?",
            (purpose,),
        )
        for (artifact_json,) in rows:
            try:
                artifact = json.loads(artifact_json)
            except (TypeError, ValueError):
                continue
            features = (artifact.get("decision_payload") or {}).get("features_by_window") or {}
            if window == "all":
                blocks = [b for b in features.values() if isinstance(b, dict)]
            else:
                block = features.get(window)
                blocks = [block] if isinstance(block, dict) else []
            for block in blocks:
                risk = block.get("risk") or {}
                evaluations = risk.get("gate_evaluations") or []
                if isinstance(evaluations, list):
                    yield evaluations
    finally:
        conn.close()


def collect(db_path: Path, purpose: str, window: str) -> tuple[int, dict[str, Counter]]:
    """Tally gate outcomes. ``observations`` counts window-observations, not rows."""
    per_gate: dict[str, Counter] = defaultdict(Counter)
    observations = 0
    for evaluations in _iter_gate_rows(db_path, purpose, window):
        observations += 1
        for record in evaluations:
            if not isinstance(record, dict):
                continue
            gate = str(record.get("gate") or "?")
            outcome = str(record.get("outcome") or "?")
            per_gate[gate][outcome] += 1
    return observations, per_gate


def _render_text(observations: int, per_gate: dict[str, Counter], window: str) -> str:
    seen = [o for o in _OUTCOME_ORDER if any(o in c for c in per_gate.values())]
    extra = sorted({o for c in per_gate.values() for o in c} - set(seen))
    columns = seen + extra

    header = ["gate", *columns, "unknown%"]
    lines = [f"window={window}  observations={observations}", "  ".join(header)]
    for gate in sorted(per_gate):
        counts = per_gate[gate]
        total = sum(counts.values())
        unknown = counts.get("skipped", 0) + counts.get("unevaluable", 0)
        pct = (unknown / total * 100.0) if total else 0.0
        cells = [gate, *[str(counts.get(c, 0)) for c in columns], f"{pct:.1f}%"]
        lines.append("  ".join(cells))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/db/data.db", type=Path)
    parser.add_argument("--purpose", default="ACCUMULATION_DISCOVERY")
    parser.add_argument(
        "--window",
        default="7",
        help="feature window id (e.g. 7, 30, 90) or 'all' to pool every window",
    )
    parser.add_argument("--format", default="text", choices=("text", "json"))
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 2

    observations, per_gate = collect(args.db, args.purpose, args.window)

    if args.format == "json":
        payload = {
            "db": str(args.db),
            "purpose": args.purpose,
            "window": args.window,
            "observations": observations,
            "gates": {gate: dict(counts) for gate, counts in sorted(per_gate.items())},
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_text(observations, per_gate, args.window))
    return 0


if __name__ == "__main__":  # pragma: no cover — operator entry point
    raise SystemExit(main())
