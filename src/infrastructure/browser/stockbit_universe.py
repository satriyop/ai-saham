"""
StockbitUniverseProvider — live IDX index universe lists from Stockbit Exodus API.

Discovery flow:
  1. GET /emitten/sectors/88/subsectors  → map subsector name → id
  2. GET /emitten/v3/sector/88/subsector/{id}/company → ticker list

Sector 88 = "Indonesia Index Universes" on Stockbit.

Known subsector IDs (from docs/stockbit_api_end_point.md):
  LQ45   → 550    IDX30  → 559    JII  → 551
  MBX    → 552    BUMN20 → 1000000011    IHSG → 467

IDX80 ID is discovered at runtime via the subsectors endpoint.

Layer: Infrastructure
Depends on: playwright_stockbit (for token)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_SUBSECTORS_URL = "https://exodus.stockbit.com/emitten/sectors/88/subsectors"
_COMPANY_URL = "https://exodus.stockbit.com/emitten/v3/sector/88/subsector/{id}/company"

# Known subsector IDs — used as fast-path fallback if discovery fails.
_KNOWN_IDS: dict[str, int | str] = {
    "lq45":       550,
    "idx30":      559,
    "jii":        551,
    "mbx":        552,
    "bumn20":     1000000011,
    "ihsg":       467,
}

# Name fragments used for fuzzy matching against Stockbit's subsector names.
# Key = our universe key, value = substrings to match (case-insensitive, any match wins).
_NAME_HINTS: dict[str, list[str]] = {
    "lq45":       ["lq45", "lq 45"],
    "idx30":      ["idx30", "idx 30"],
    "idx80":      ["idx80", "idx 80"],
    "jii":        ["jii", "jakarta islamic"],
    "mbx":        ["mbx"],
    "bumn20":     ["bumn20", "bumn 20"],
    "ihsg":       ["ihsg", "composite", "issi"],
}


def _match_subsector(name: str) -> str | None:
    """Return our universe key if name matches any hint, else None."""
    lower = name.lower()
    for key, hints in _NAME_HINTS.items():
        if any(h in lower for h in hints):
            return key
    return None


class StockbitUniverseProvider:
    """
    Fetches live IDX index universe constituent lists from Stockbit.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
    """

    def __init__(self, broker_provider: "StockbitPlaywrightBrokerProvider") -> None:
        self._provider = broker_provider
        self._subsector_map: dict[str, int | str] | None = None  # universe key → id

    # ── Internal helpers ────────────────────────────────────────────────────

    def _get(self, url: str) -> dict | None:
        from src.infrastructure.browser.playwright_stockbit import _exodus_get
        token = self._provider._get_token()
        return _exodus_get(url, token)

    def _discover_subsectors(self) -> dict[str, int | str]:
        """Call /emitten/sectors/88/subsectors and build universe_key → subsector_id map.

        Falls back to _KNOWN_IDS for any universe not found via discovery.
        """
        result: dict[str, int | str] = dict(_KNOWN_IDS)

        try:
            body = self._get(_SUBSECTORS_URL)
            if not body:
                logger.debug("Empty subsectors response — using known IDs only")
                return result

            # Try common response shapes
            items: list = []
            data = body.get("data")
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                # Some endpoints nest further: data.subsectors[]
                for key in ("subsectors", "list", "items", "results"):
                    if isinstance(data.get(key), list):
                        items = data[key]
                        break

            if not items:
                logger.debug("Could not extract subsector list from response: %s", list(body.keys()))
                return result

            for item in items:
                if not isinstance(item, dict):
                    continue
                subsector_id = item.get("id") or item.get("subsector_id")
                name = str(item.get("name") or item.get("subsector_name") or "")
                if not subsector_id or not name:
                    continue

                key = _match_subsector(name)
                if key:
                    result[key] = subsector_id
                    logger.debug("Discovered subsector: %s → id=%s (%s)", key, subsector_id, name)

            # Log any discovered universes we didn't know before
            for key, sid in result.items():
                if key not in _KNOWN_IDS:
                    logger.info("New universe discovered via API: %s → %s", key, sid)

        except Exception as e:
            logger.warning("Subsector discovery failed: %s — using known IDs", e)

        return result

    def _fetch_tickers(self, subsector_id: int | str) -> list[str]:
        """Fetch all ticker symbols for a given subsector ID."""
        url = _COMPANY_URL.format(id=subsector_id)
        try:
            body = self._get(url)
            if not body:
                return []

            # Try common response shapes for company lists
            items: list = []
            data = body.get("data")
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                for key in ("companies", "list", "items", "results", "stocks"):
                    if isinstance(data.get(key), list):
                        items = data[key]
                        break

            tickers: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Stockbit uses various field names for ticker symbol
                code = (
                    item.get("ticker")
                    or item.get("code")
                    or item.get("stock_code")
                    or item.get("symbol")
                    or (item.get("stock_detail") or {}).get("code")
                )
                if code and isinstance(code, str) and code.strip():
                    tickers.append(code.strip().upper())

            return sorted(set(tickers))

        except Exception as e:
            logger.warning("Ticker fetch failed for subsector %s: %s", subsector_id, e)
            return []

    # ── Public API ───────────────────────────────────────────────────────────

    def list_available(self) -> dict[str, int | str]:
        """Return the discovered universe_key → subsector_id map.

        Runs discovery once and caches the result for the lifetime of this instance.
        """
        if self._subsector_map is None:
            self._subsector_map = self._discover_subsectors()
        return self._subsector_map

    def fetch(self, universe_key: str) -> list[str]:
        """Return sorted list of ticker symbols for the named universe.

        Args:
            universe_key: One of 'lq45', 'idx30', 'idx80', 'jii', 'mbx',
                          'bumn20', or any key from list_available().

        Returns:
            Sorted list of ticker symbols, or [] if unavailable.
        """
        available = self.list_available()
        subsector_id = available.get(universe_key.lower())
        if not subsector_id:
            logger.warning("No subsector ID for universe '%s' — run discovery first", universe_key)
            return []

        tickers = self._fetch_tickers(subsector_id)
        logger.info("Universe '%s': %d tickers", universe_key, len(tickers))
        return tickers

    def fetch_all(
        self,
        keys: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Fetch ticker lists for multiple universes in one call.

        Args:
            keys: Universe keys to fetch. Defaults to all discovered universes.

        Returns:
            dict of universe_key → sorted ticker list (empty list on failure).
        """
        available = self.list_available()
        targets = keys if keys else list(available.keys())
        return {k: self.fetch(k) for k in targets}
