"""Local-only cache health snapshot for TUI session rail.

Reads SQLite date ranges only — no network, no provider probes.
Suitable for cockpit mount/refresh (ADR-051 local-first).

Layer: Adapter (pure DTO + format + thin repo reads via callables)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

HealthStatus = Literal["ready", "empty", "lag", "unknown"]


@dataclass(frozen=True)
class LocalCacheHealth:
    universe: str
    candle_as_of: str
    broker_as_of: str
    status: HealthStatus
    next_step: str
    detail: str = ""

    def sidebar_cache_line(self) -> str:
        return format_sidebar_cache_line(self)

    def sidebar_next_line(self) -> str:
        return format_sidebar_next_line(self)


def format_sidebar_cache_line(health: LocalCacheHealth) -> str:
    """Single sidebar line for Cache row."""
    if health.status == "empty":
        return "Cache    empty"
    if health.status == "unknown":
        return "Cache    unknown"
    c = health.candle_as_of or "—"
    b = health.broker_as_of or "—"
    if health.status == "lag":
        return f"Cache    candle {c} · broker {b} · LAG"
    return f"Cache    candle {c} · broker {b}"


def format_sidebar_next_line(health: LocalCacheHealth) -> str:
    """Cue for Online / next-step row (explicit fetch only)."""
    step = (health.next_step or "").strip()
    if not step:
        return "Fetch is explicit."
    return step


def assess_local_cache_health(
    *,
    universe: str,
    candle_latest: date | None,
    broker_latest: date | None,
    lag_days: int = 1,
) -> LocalCacheHealth:
    """Pure policy: map local dates → status + next-step cue."""
    uni = (universe or "local").strip().lower() or "local"
    c_s = candle_latest.isoformat() if candle_latest else ""
    b_s = broker_latest.isoformat() if broker_latest else ""

    if candle_latest is None and broker_latest is None:
        return LocalCacheHealth(
            universe=uni,
            candle_as_of="",
            broker_as_of="",
            status="empty",
            next_step="Next: Ctrl+P · Fetch market data (explicit)",
            detail="no local candle or broker dates",
        )

    if candle_latest is None:
        return LocalCacheHealth(
            universe=uni,
            candle_as_of="",
            broker_as_of=b_s,
            status="empty",
            next_step="Next: Ctrl+P · Fetch market data (explicit)",
            detail="no local candles",
        )

    if broker_latest is None:
        return LocalCacheHealth(
            universe=uni,
            candle_as_of=c_s,
            broker_as_of="",
            status="lag",
            next_step="Next: CLI saham fetch broker (explicit) or palette Fetch",
            detail="candles present · broker missing",
        )

    delta = abs((candle_latest - broker_latest).days)
    if delta > lag_days:
        return LocalCacheHealth(
            universe=uni,
            candle_as_of=c_s,
            broker_as_of=b_s,
            status="lag",
            next_step="Next: explicit fetch if board looks stale (Ctrl+P Fetch)",
            detail=f"candle/broker gap {delta}d",
        )

    return LocalCacheHealth(
        universe=uni,
        candle_as_of=c_s,
        broker_as_of=b_s,
        status="ready",
        next_step="Fetch is explicit.",
        detail="local cache dates present",
    )


def load_local_cache_health(
    *,
    universe: str,
    get_candle_latest: Callable[[], date | None],
    get_broker_latest: Callable[[], date | None],
    lag_days: int = 1,
) -> LocalCacheHealth:
    """Load health via injected local callables (no network)."""
    try:
        candle = get_candle_latest()
    except Exception:
        candle = None
    try:
        broker = get_broker_latest()
    except Exception:
        broker = None
    if candle is None and broker is None:
        # Distinguish total failure from empty DB when both raise
        return LocalCacheHealth(
            universe=(universe or "local").strip().lower() or "local",
            candle_as_of="",
            broker_as_of="",
            status="unknown",
            next_step="Next: Ctrl+P · Fetch market data (explicit)",
            detail="local health read failed or empty",
        )
    return assess_local_cache_health(
        universe=universe,
        candle_latest=candle,
        broker_latest=broker,
        lag_days=lag_days,
    )
