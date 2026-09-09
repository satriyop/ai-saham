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

from src.domain.value_objects.idx_market import (
    IDX_TIMEZONE,
    NCP_LOCK_TIME,
    PRE_OPEN_MATCHING_START,
    PRE_OPEN_START,
)
from src.domain.value_objects.idx_market import REGULAR_OPEN as PRE_OPEN_END
from src.domain.value_objects.market_status import MarketStatus

_NCP_LOCK_WINDOW = f"{NCP_LOCK_TIME.strftime('%H:%M')}–{PRE_OPEN_MATCHING_START.strftime('%H:%M')}"
_PRE_OPEN_WINDOW = f"{PRE_OPEN_START.strftime('%H:%M')}-{PRE_OPEN_END.strftime('%H:%M')}"


@dataclass(frozen=True)
class PreOpenRunGuard:
    """Runtime guard for pre-open workflow timing."""

    run_at: datetime
    warnings: tuple[str, ...] = ()
    error: str | None = None
    outside_window: bool = False
    is_trading_day: bool = True
    in_ncp_lock_window: bool = False
    late_wake: bool = False

    def capture_rejection(self) -> str | None:
        """Authoritative-capture fail-closed reason, or None if the start is in lock."""
        if self.late_wake:
            return (
                f"Capture rejected: late wake — NCP lock {_NCP_LOCK_WINDOW} "
                "Asia/Jakarta already missed. No authoritative capture."
            )
        if not self.in_ncp_lock_window:
            return (
                f"Capture rejected: outside the {_NCP_LOCK_WINDOW} NCP "
                f"locked-input window (IDX pre-open is {_PRE_OPEN_WINDOW} "
                "Asia/Jakarta). Authoritative capture requires a live "
                "collection wholly inside the same-session lock."
            )
        return None


def _non_trading_block(
    *,
    run_at: datetime,
    message: str,
    in_pre_open_window: bool,
    in_ncp_lock_window: bool,
) -> PreOpenRunGuard:
    return PreOpenRunGuard(
        run_at=run_at,
        error=message,
        is_trading_day=False,
        outside_window=not in_pre_open_window,
        in_ncp_lock_window=in_ncp_lock_window,
        late_wake=False,
    )


def build_pre_open_run_guard(
    *,
    run_at: datetime,
    market_status: MarketStatus,
    allow_non_trading_day: bool = False,
    same_day_auction_evidence: bool = False,
) -> PreOpenRunGuard:
    warnings: list[str] = []
    local_run_at = run_at.astimezone(IDX_TIMEZONE)
    current_time = local_run_at.time()
    is_trading_day = True
    in_pre_open_window = PRE_OPEN_START <= current_time < PRE_OPEN_END
    in_ncp_lock_window = NCP_LOCK_TIME <= current_time < PRE_OPEN_MATCHING_START
    local_is_weekend = local_run_at.weekday() in (5, 6)
    stockbit_closed = (
        market_status.source == "stockbit"
        and not market_status.is_open
        and not market_status.is_pre_open
    )
    # Stockbit never emits Weekend; closed/no-FCA is always Post-Market
    # (holiday, after-hours, and NCP lock). NCP lock is only the in-window
    # Post-Market case with same-day IEV rows proving the board opened.
    ncp_lock_exception = stockbit_closed and in_pre_open_window and same_day_auction_evidence

    if market_status.source == "stockbit":
        if market_status.is_weekend or local_is_weekend:
            is_trading_day = False
            message = (
                f"{local_run_at.date()} is a non-trading day "
                f"({market_status.session_name} per Stockbit). "
                "Use --allow-non-trading-day only for dry-runs/backfills."
            )
            if not allow_non_trading_day:
                return _non_trading_block(
                    run_at=local_run_at,
                    message=message,
                    in_pre_open_window=in_pre_open_window,
                    in_ncp_lock_window=in_ncp_lock_window,
                )
            warnings.append(message)
        elif ncp_lock_exception:
            warnings.append(
                "Stockbit reports "
                f"{market_status.session_name} during the IDX pre-open window; "
                "treating as NCP lock or stale status, not a non-trading day."
            )
        elif stockbit_closed:
            is_trading_day = False
            message = (
                f"{local_run_at.date()} is a non-trading day "
                f"({market_status.session_name} per Stockbit). "
                "Use --allow-non-trading-day only for dry-runs/backfills."
            )
            if not allow_non_trading_day:
                return _non_trading_block(
                    run_at=local_run_at,
                    message=message,
                    in_pre_open_window=in_pre_open_window,
                    in_ncp_lock_window=in_ncp_lock_window,
                )
            warnings.append(message)
    elif local_is_weekend:
        is_trading_day = False
        message = (
            f"{local_run_at.date()} is a weekend. "
            "Use --allow-non-trading-day only for dry-runs/backfills."
        )
        if not allow_non_trading_day:
            return _non_trading_block(
                run_at=local_run_at,
                message=message,
                in_pre_open_window=in_pre_open_window,
                in_ncp_lock_window=in_ncp_lock_window,
            )
        warnings.append(message)

    outside_window = not in_pre_open_window
    if outside_window:
        warnings.append(
            f"Current Asia/Jakarta time is outside IDX pre-open window {_PRE_OPEN_WINDOW}."
        )

    late_wake = is_trading_day and current_time >= PRE_OPEN_MATCHING_START
    return PreOpenRunGuard(
        run_at=local_run_at,
        warnings=tuple(warnings),
        outside_window=outside_window,
        is_trading_day=is_trading_day,
        in_ncp_lock_window=in_ncp_lock_window,
        late_wake=late_wake,
    )
