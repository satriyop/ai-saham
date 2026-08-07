"""Filesystem helpers for swing_trade_plan latest-file handoff.

Layer: Application (paths + JSON only; no providers).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.domain.value_objects.swing_trade_plan import (
    SwingTradePlan,
)


def plans_dir_from_journal_path(journal_path: Path) -> Path:
    """Sibling ``plans/`` next to the accumulation journal CSV."""
    return Path(journal_path).expanduser().resolve().parent / "plans"


def latest_plan_path(plans_dir: Path, ticker: str) -> Path:
    return Path(plans_dir) / f"{ticker.upper()}_latest.json"


def save_swing_trade_plan(plan: SwingTradePlan, plans_dir: Path) -> Path:
    """Write plan JSON and return path of the latest file for the ticker."""
    plans_dir = Path(plans_dir)
    plans_dir.mkdir(parents=True, exist_ok=True)
    latest = latest_plan_path(plans_dir, plan.ticker)
    payload = plan.to_dict()
    latest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Also keep an immutable copy by plan_id
    by_id = plans_dir / f"{plan.ticker.upper()}_{plan.plan_id}.json"
    by_id.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return latest


def load_swing_trade_plan(path: Path) -> SwingTradePlan:
    """Load one strict schema-2 swing_trade_plan artifact."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("plan file must contain a JSON object")
    return SwingTradePlan.from_dict(raw)


def resolve_from_plan_path(
    *,
    ticker: str,
    from_plan: str | None,
    plans_dir: Path,
) -> Path:
    """Resolve --from-plan value to a filesystem path.

    - omitted / empty / \"latest\" → ``{TICKER}_latest.json``
    - otherwise treat as path
    """
    if from_plan is None or from_plan.strip() == "" or from_plan.strip().lower() == "latest":
        path = latest_plan_path(plans_dir, ticker)
    else:
        path = Path(from_plan).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"swing trade plan not found: {path}")
    return path
