"""
Pre-open workflow run-guard policy.

Decides whether a pre-open screen run is allowed given the current IDX
market status and wall-clock time, independent of any CLI or infrastructure
concerns.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.value_objects.idx_market import IDX_TIMEZONE, PRE_OPEN_START
from src.domain.value_objects.idx_market import REGULAR_OPEN as PRE_OPEN_END
from src.domain.value_objects.market_status import MarketStatus


@dataclass(frozen=True)
class PreOpenRunGuard:
    """Runtime guard for pre-open workflow timing."""

    run_at: datetime
    warnings: tuple[str, ...] = ()
    error: str | None = None


def build_pre_open_run_guard(
    *,
    run_at: datetime,
    market_status: MarketStatus,
    allow_non_trading_day: bool = False,
) -> PreOpenRunGuard:
    warnings: list[str] = []
    local_run_at = run_at.astimezone(IDX_TIMEZONE)

    if market_status.source == "stockbit":
        if not market_status.is_open and not market_status.is_pre_open:
            message = (
                f"{local_run_at.date()} is a non-trading day "
                f"({market_status.session_name} per Stockbit). "
                "Use --allow-non-trading-day only for dry-runs/backfills."
            )
            if not allow_non_trading_day:
                return PreOpenRunGuard(run_at=local_run_at, error=message)
            warnings.append(message)
    else:
        # Heuristic/wall-clock fallback
        is_weekend = local_run_at.weekday() in (5, 6)
        if is_weekend:
            message = (
                f"{local_run_at.date()} is a weekend. "
                "Use --allow-non-trading-day only for dry-runs/backfills."
            )
            if not allow_non_trading_day:
                return PreOpenRunGuard(run_at=local_run_at, error=message)
            warnings.append(message)

    # Pre-open window timing warning
    current_time = local_run_at.time()
    if not (PRE_OPEN_START <= current_time < PRE_OPEN_END):
        warnings.append(
            "Current Asia/Jakarta time is outside IDX pre-open window "
            f"{PRE_OPEN_START.strftime('%H:%M')}-{PRE_OPEN_END.strftime('%H:%M')}."
        )

    return PreOpenRunGuard(run_at=local_run_at, warnings=tuple(warnings))
