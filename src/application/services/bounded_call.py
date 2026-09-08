"""Bound a blocking call and record hung-fetch rate.

A hung provider call must fail the caller cleanly. The worker is a daemon so
the process can exit; it is not killed silently — the timeout is logged.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable, TypeVar

from src.domain.value_objects.idx_market import IDX_TIMEZONE

logger = logging.getLogger(__name__)

T = TypeVar("T")

HANG_RATE_LOG = Path("logs") / "fetch_hang_rate.jsonl"


class CallTimeout(Exception):
    """Raised when a bounded call does not return before its deadline."""


@dataclass(frozen=True)
class HangRateRecord:
    surface: str
    attempted: int
    hung: int
    rate: float
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "at": datetime.now(IDX_TIMEZONE).isoformat(),
            "surface": self.surface,
            "attempted": self.attempted,
            "hung": self.hung,
            "rate": self.rate,
            "note": self.note,
        }


def call_bounded(fn: Callable[[], T], timeout_s: float) -> T:
    """Run ``fn`` and raise CallTimeout if it is still running after ``timeout_s``.

    The worker is a daemon thread. On timeout the caller proceeds and the
    timeout is visible — the process is not silently killed.
    """
    if timeout_s <= 0:
        raise CallTimeout(f"deadline already elapsed ({timeout_s:.3f}s)")

    box: dict[str, object] = {}

    def runner() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 — re-raised on the caller thread
            box["error"] = exc

    worker = threading.Thread(target=runner, daemon=True, name="bounded-call")
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        logger.warning("bounded call exceeded %.1fs", timeout_s)
        raise CallTimeout(f"call exceeded {timeout_s:.1f}s")
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["value"]  # type: ignore[return-value]


def log_hang_rate(record: HangRateRecord, *, path: Path | None = None) -> Path:
    """Append one hang-rate line. Never raises (logging must not fail the fetch)."""
    payload = record.to_dict()
    logger.warning(
        "hung-fetch surface=%s hung=%s attempted=%s rate=%.4f %s",
        record.surface,
        record.hung,
        record.attempted,
        record.rate,
        record.note,
    )
    target = path or HANG_RATE_LOG
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError as exc:
        logger.warning("hung-fetch rate log write failed: %s", exc)
    return target


# Morning desk must finish or fail before the 08:56 WIB NCP lock.
MORNING_CUTOFF = time(8, 55, 30)
NCP_LOCK = time(8, 56)
CANDLES_ONLY_CALL_TIMEOUT_S = 20.0
CANDLES_ONLY_WALL_S = 45.0
MARKET_STATUS_TIMEOUT_S = 8.0


def candles_only_deadline(now: datetime | None = None) -> tuple[float, str]:
    """Return (monotonic deadline, note) for a candles-only refresh.

    Before 08:56 WIB the wall is the earlier of 45s and 08:55:30 so the fetch
    cannot still be running when the NCP window opens. After that, 45s only —
    enough to stop a ~90s hang, not a silent kill.
    """
    import time as _time

    now = now or datetime.now(IDX_TIMEZONE)
    remaining = CANDLES_ONLY_WALL_S
    note = f"wall={CANDLES_ONLY_WALL_S:.0f}s"
    if now.timetz().replace(tzinfo=None) < NCP_LOCK:
        cutoff = datetime.combine(now.date(), MORNING_CUTOFF, tzinfo=IDX_TIMEZONE)
        seconds_to_cutoff = (cutoff - now).total_seconds()
        remaining = min(CANDLES_ONLY_WALL_S, max(1.0, seconds_to_cutoff))
        note = f"before-0856 remaining={remaining:.1f}s"
    return _time.monotonic() + remaining, note
