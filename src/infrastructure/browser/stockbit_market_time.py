"""
Market status providers for IDX.

LocalClockMarketStatusProvider — offline fallback; derives status from
  wall-clock time in Asia/Jakarta. Consolidates the time-based logic that
  was previously duplicated across intraday_workflow_commands.py,
  learn_opening_commands.py, and collect_iev().

StockbitMarketTimeProvider — canonical live implementation; calls
  GET /company-price-feed/market-time and returns STATUS_OPEN / STATUS_CLOSE
  from Stockbit. Falls back to LocalClockMarketStatusProvider on any failure
  (no session, network error, unexpected response shape).

TTL: 60 seconds — market sessions change on minute boundaries; no need to
  hit the API on every call within a tight loop.

Layer: Infrastructure
Depends on: playwright_stockbit (for token), MarketStatusProvider port
"""

from __future__ import annotations

import logging
import time as _time_module
from datetime import datetime, time
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from src.domain.ports.market_status_provider import MarketStatusProvider
from src.domain.value_objects.market_status import MarketStatus

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_IDX_TZ = ZoneInfo("Asia/Jakarta")
_MARKET_TIME_URL = "https://exodus.stockbit.com/company-price-feed/market-time"
_CACHE_TTL_SECONDS = 60

# Wall-clock boundaries used by LocalClockMarketStatusProvider
_PRE_OPEN_START = time(8, 45)
_REGULAR_START  = time(9, 0)
_PRE_CLOSE_START = time(15, 50)
_MARKET_CLOSE   = time(16, 0)


class LocalClockMarketStatusProvider(MarketStatusProvider):
    """Derives IDX market status from Asia/Jakarta wall clock.

    Consolidates the time-based heuristic that was previously duplicated
    across three adapter files. Used as the offline fallback when no
    Stockbit session is available.

    Session mapping (IDX regular board schedule):
      Weekend (Sat/Sun)      → STATUS_CLOSE / "Weekend"
      <08:45                 → STATUS_CLOSE / "Post-Market"  (previous day closed)
      08:45–08:59            → STATUS_CLOSE / "Pre-Open"     (call auction pending)
      09:00–15:49            → STATUS_OPEN  / "Regular"
      15:50–15:59            → STATUS_OPEN  / "Pre-Closing"
      >=16:00                → STATUS_CLOSE / "Post-Market"
    """

    def get_status(self) -> MarketStatus:
        now = datetime.now(_IDX_TZ)
        fetched_at = now
        t = now.time()

        if now.weekday() >= 5:
            return MarketStatus(
                status="STATUS_CLOSE",
                session_name="Weekend",
                is_open=False,
                session_open=None,
                session_close=None,
                fetched_at=fetched_at,
                source="local_clock",
            )

        if t < _PRE_OPEN_START:
            return MarketStatus(
                status="STATUS_CLOSE",
                session_name="Post-Market",
                is_open=False,
                session_open=None,
                session_close=None,
                fetched_at=fetched_at,
                source="local_clock",
            )

        if t < _REGULAR_START:
            return MarketStatus(
                status="STATUS_CLOSE",
                session_name="Pre-Open",
                is_open=False,
                session_open=_PRE_OPEN_START.strftime("%H:%M"),
                session_close=_REGULAR_START.strftime("%H:%M"),
                fetched_at=fetched_at,
                source="local_clock",
            )

        if t < _PRE_CLOSE_START:
            return MarketStatus(
                status="STATUS_OPEN",
                session_name="Regular",
                is_open=True,
                session_open=_REGULAR_START.strftime("%H:%M"),
                session_close=_PRE_CLOSE_START.strftime("%H:%M"),
                fetched_at=fetched_at,
                source="local_clock",
            )

        if t < _MARKET_CLOSE:
            return MarketStatus(
                status="STATUS_OPEN",
                session_name="Pre-Closing",
                is_open=True,
                session_open=_PRE_CLOSE_START.strftime("%H:%M"),
                session_close=_MARKET_CLOSE.strftime("%H:%M"),
                fetched_at=fetched_at,
                source="local_clock",
            )

        return MarketStatus(
            status="STATUS_CLOSE",
            session_name="Post-Market",
            is_open=False,
            session_open=None,
            session_close=None,
            fetched_at=fetched_at,
            source="local_clock",
        )


class StockbitMarketTimeProvider(MarketStatusProvider):
    """Canonical market status from Stockbit /company-price-feed/market-time.

    Falls back to LocalClockMarketStatusProvider on any failure so callers
    always get a valid MarketStatus regardless of session availability.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider.
        ttl: Cache lifetime in seconds (default 60).
    """

    def __init__(
        self,
        broker_provider: "StockbitPlaywrightBrokerProvider",
        ttl: int = _CACHE_TTL_SECONDS,
    ) -> None:
        self._provider = broker_provider
        self._ttl = ttl
        self._cache: MarketStatus | None = None
        self._cache_at: float = 0.0
        self._fallback = LocalClockMarketStatusProvider()

    def get_status(self) -> MarketStatus:
        now_ts = _time_module.monotonic()
        if self._cache and (now_ts - self._cache_at) < self._ttl:
            return self._cache

        result = self._fetch()
        if result:
            self._cache = result
            self._cache_at = now_ts
            return result

        # Fallback — but don't cache fallback results; retry API next call
        return self._fallback.get_status()

    def _fetch(self) -> MarketStatus | None:
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            body = _exodus_get(_MARKET_TIME_URL, token)
            if not body:
                logger.debug("Empty market-time response")
                return None
            return self._parse(body)
        except Exception as e:
            logger.debug("market-time fetch failed: %s", e)
            return None

    def _parse(self, body: dict) -> MarketStatus | None:
        """Parse Stockbit market-time response defensively.

        The exact field names are not yet confirmed from a live probe —
        this implementation tries common variants. Run `saham fetch stockbit spy`
        and check /company-price-feed/market-time to confirm and tighten.
        """
        # Unwrap common envelope shapes
        data = body.get("data") if isinstance(body.get("data"), dict) else body

        # status field — try several names
        raw_status = (
            data.get("status")
            or data.get("market_status")
            or data.get("marketStatus")
            or ""
        )
        raw_status = str(raw_status).upper()
        is_open = "OPEN" in raw_status and "CLOSE" not in raw_status

        # Normalise to canonical strings
        status = "STATUS_OPEN" if is_open else "STATUS_CLOSE"

        # session name — Stockbit may use various field names
        session_name = (
            data.get("session_name")
            or data.get("sessionName")
            or data.get("session")
            or data.get("market_session")
            or data.get("name")
            or "Unknown"
        )
        session_name = str(session_name)

        # Session times — optional
        session_open = (
            data.get("open_time")
            or data.get("openTime")
            or data.get("session_open")
            or None
        )
        session_close = (
            data.get("close_time")
            or data.get("closeTime")
            or data.get("session_close")
            or None
        )

        if not raw_status:
            logger.debug("market-time: could not extract status from %s", list(body.keys()))
            return None

        return MarketStatus(
            status=status,
            session_name=session_name,
            is_open=is_open,
            session_open=str(session_open) if session_open else None,
            session_close=str(session_close) if session_close else None,
            fetched_at=datetime.now(_IDX_TZ),
            source="stockbit",
        )


# ── File cache ───────────────────────────────────────────────────────────────

_CACHE_FILE = Path(".market_status.json")
_CACHE_MAX_AGE_SECONDS = 300  # 5 minutes — sessions change on minute boundaries


def read_cached_market_status(max_age_seconds: int = _CACHE_MAX_AGE_SECONDS) -> MarketStatus | None:
    """Read market status from the file cache written by `saham today`.

    Returns None if the cache file is missing, unreadable, or older than max_age_seconds.
    Never raises.
    """
    import json
    try:
        if not _CACHE_FILE.exists():
            return None
        raw = json.loads(_CACHE_FILE.read_text())
        fetched_at_str = raw.get("fetched_at", "")
        fetched_at = datetime.fromisoformat(fetched_at_str)
        age = (datetime.now(_IDX_TZ) - fetched_at).total_seconds()
        if age > max_age_seconds:
            return None
        return MarketStatus(
            status=raw["status"],
            session_name=raw["session_name"],
            is_open=raw["is_open"],
            session_open=raw.get("session_open"),
            session_close=raw.get("session_close"),
            fetched_at=fetched_at,
            source=raw["source"],
        )
    except Exception:
        return None


def write_market_status_cache(status: MarketStatus) -> None:
    """Write a Stockbit-confirmed MarketStatus to the file cache.

    Only call this when status.source == 'stockbit'. Never raises.
    """
    import json
    try:
        data = {
            "status": status.status,
            "session_name": status.session_name,
            "is_open": status.is_open,
            "session_open": status.session_open,
            "session_close": status.session_close,
            "fetched_at": status.fetched_at.isoformat(),
            "source": status.source,
        }
        _CACHE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


# ── Module-level convenience functions ───────────────────────────────────────

def get_display_market_status() -> MarketStatus:
    """Return market status for display in command headers — instant, no network.

    Read order:
      1. File cache (written by `saham today`) — if present and < 5 min old
      2. Local clock fallback

    Never tries Stockbit directly. All commands that only need a status line
    for display context should use this.
    """
    cached = read_cached_market_status()
    if cached:
        return cached
    return LocalClockMarketStatusProvider().get_status()


def fetch_and_cache_market_status() -> MarketStatus | None:
    """Fetch market status from Stockbit and write to cache on success.

    Returns the MarketStatus on success (source='stockbit'), or None if
    Stockbit is unavailable or the response could not be parsed.
    Does NOT fall back to local clock — callers handle the None case explicitly
    so they can show a clear message to the user.
    """
    try:
        from pathlib import Path
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        if not Path(".stockbit_profile").exists():
            return None
        provider = StockbitPlaywrightBrokerProvider()
        if not provider.is_authenticated():
            return None
        result = StockbitMarketTimeProvider(broker_provider=provider).get_status()
        if result and result.source == "stockbit":
            write_market_status_cache(result)
            return result
        return None
    except Exception:
        return None


def get_current_market_status() -> MarketStatus:
    """Return current IDX market status for commands that already hold a Stockbit token.

    Read order:
      1. File cache (fresh < 5 min)
      2. Stockbit live (token already cached in-process from earlier in the same command)
      3. Local clock

    Use this in commands that already use Stockbit (pre-open, learn snapshot)
    where the token acquisition cost is already paid.
    """
    cached = read_cached_market_status()
    if cached:
        return cached
    try:
        from pathlib import Path
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        if Path(".stockbit_profile").exists():
            provider = StockbitPlaywrightBrokerProvider()
            if provider.is_authenticated():
                result = StockbitMarketTimeProvider(broker_provider=provider).get_status()
                if result.source == "stockbit":
                    write_market_status_cache(result)
                    return result
    except Exception:
        pass
    return LocalClockMarketStatusProvider().get_status()


def format_market_status_line(status: MarketStatus) -> str:
    """Return a compact one-line market status string for command output headers.

    Examples:
      Market: Pre-Open    08:47 WIB  [stockbit]
      Market: Regular     09:15 WIB  [stockbit]  ⚠ open — EOD data not final
      Market: Post-Market 16:32 WIB  [local_clock]
    """
    now_wib = datetime.now(_IDX_TZ)
    time_str = now_wib.strftime("%H:%M WIB")
    source_tag = f"[{status.source}]"
    line = f"Market: {status.session_name:<14} {time_str}  {source_tag}"
    if status.is_open and status.is_regular:
        line += "  ⚠ open — EOD data not yet final"
    return line
