"""
StockbitUniverseProvider — live IDX index universe lists from Stockbit Exodus API.

Discovery flow:
  1. GET /emitten/sectors/88/subsectors  → broad index universes (LQ45, IDX30, IDX80, etc.)
     GET /emitten/sectors/70/subsectors  → sectoral index universes (Finance, Energy, etc.)
  2. GET /emitten/v3/sector/{sector}/subsector/{id}/company → ticker list

Sector 88 = "Indonesia Index Universes" (LQ45, IDX30, IDX80, JII, MBX, BUMN20, IHSG)
Sector 70 = "Indeks Sektoral" (11 official IDX sectoral indices)

Known subsector IDs (from docs/stockbit_api_end_point.md):
  LQ45   → 550    IDX30  → 559    JII  → 551
  MBX    → 552    BUMN20 → 1000000011    IHSG → 467

IDX80 and sectoral IDs are discovered at runtime via the subsectors endpoints.

Layer: Infrastructure
Depends on: playwright_stockbit (for token)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_SECTOR_88_URL = "https://exodus.stockbit.com/emitten/sectors/88/subsectors"
_SECTOR_70_URL = "https://exodus.stockbit.com/emitten/sectors/70/subsectors"
_COMPANY_URL = "https://exodus.stockbit.com/emitten/v3/sector/{sector}/subsector/{id}/company"
_SCREENER_UNIVERSE_URL = "https://exodus.stockbit.com/screener/universe"

# Known subsector IDs for sector 88 — used as fast-path fallback if discovery fails.
_KNOWN_IDS: dict[str, int | str] = {
    "lq45":   550,
    "idx30":  559,
    "jii":    551,
    "mbx":    552,
    "bumn20": 1000000011,
    "ihsg":   467,
}

# Universe type by key — used for display in update command.
_UNIVERSE_TYPE: dict[str, str] = {
    "lq45":       "broad",
    "idx30":      "broad",
    "idx80":      "broad",
    "jii":        "broad",
    "mbx":        "broad",
    "bumn20":     "broad",
    "ihsg":       "broad",
    "finance":    "sectoral",
    "energy":     "sectoral",
    "basic":      "sectoral",
    "industrial": "sectoral",
    "infra":      "sectoral",
    "tech":       "sectoral",
    "health":     "sectoral",
    "noncyc":     "sectoral",
    "cyclic":     "sectoral",
    "property":   "sectoral",
    "transport":  "sectoral",
}

# Broad index name hints — sector 88 (case-insensitive substring match)
_BROAD_NAME_HINTS: dict[str, list[str]] = {
    "lq45":   ["lq45", "lq 45"],
    "idx30":  ["idx30", "idx 30"],
    "idx80":  ["idx80", "idx 80"],
    "jii":    ["jii", "jakarta islamic"],
    "mbx":    ["mbx"],
    "bumn20": ["bumn20", "bumn 20"],
    "ihsg":   ["ihsg", "composite", "issi"],
}

# Sectoral index name hints — sector 70 (Indonesian + English, case-insensitive)
_SECTORAL_NAME_HINTS: dict[str, list[str]] = {
    "finance":    ["keuangan", "finance"],
    "energy":     ["energi", "energy"],
    "basic":      ["barang baku", "basic material"],
    "industrial": ["perindustrian", "industrial"],
    "infra":      ["infrastruktur", "infrastructure"],
    "tech":       ["teknologi", "technology", "techno"],
    "health":     ["kesehatan", "health"],
    "noncyc":     ["kebutuhan primer", "non-cyclic", "noncyc"],
    "cyclic":     ["barang konsumen", "cyclic", "consumer cycl"],
    "property":   ["properti", "property", "real estate"],
    "transport":  ["transportasi", "transport", "logistik"],
}


def _match_hints(name: str, hints: dict[str, list[str]]) -> str | None:
    """Return universe key if name matches any hint in the given dict, else None."""
    lower = name.lower()
    for key, fragments in hints.items():
        if any(f in lower for f in fragments):
            return key
    return None


def universe_type(key: str) -> Literal["broad", "sectoral", "unknown"]:
    """Return the type label for a universe key."""
    return _UNIVERSE_TYPE.get(key.lower(), "unknown")  # type: ignore[return-value]


class StockbitUniverseProvider:
    """
    Fetches live IDX index universe constituent lists from Stockbit.

    Discovers universes from two sectors:
      - Sector 88: broad market indices (LQ45, IDX30, IDX80, JII, MBX, BUMN20)
      - Sector 70: sectoral indices (Finance, Energy, Healthcare, etc.)

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
    """

    def __init__(self, broker_provider: "StockbitPlaywrightBrokerProvider") -> None:
        self._provider = broker_provider
        self._subsector_map: dict[str, tuple[int | str, int]] | None = None  # key → (id, sector)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _get(self, url: str) -> dict | None:
        from src.infrastructure.browser.playwright_stockbit import _exodus_get
        token = self._provider._get_token()
        return _exodus_get(url, token)

    def _parse_subsector_items(self, body: dict | None) -> list[dict]:
        """Extract the list of subsector items from a sectors API response."""
        if not body:
            return []
        items: list = []
        data = body.get("data")
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ("subsectors", "list", "items", "results"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
        return [i for i in items if isinstance(i, dict)]

    def _discover_sector(
        self,
        url: str,
        sector_num: int,
        hints: dict[str, list[str]],
        result: dict[str, tuple[int | str, int]],
    ) -> None:
        """Discover subsectors for one sector URL and merge matches into result."""
        try:
            body = self._get(url)
            items = self._parse_subsector_items(body)
            if not items:
                logger.debug("No subsector items from %s", url)
                return
            for item in items:
                sid = item.get("id") or item.get("subsector_id")
                name = str(item.get("name") or item.get("subsector_name") or "")
                if not sid or not name:
                    continue
                key = _match_hints(name, hints)
                if key and key not in result:
                    result[key] = (sid, sector_num)
                    logger.debug("Discovered [sector %d] %s → id=%s (%s)", sector_num, key, sid, name)
        except Exception as e:
            logger.warning("Sector %d discovery failed: %s", sector_num, e)

    def _discover_subsectors(self) -> dict[str, tuple[int | str, int]]:
        """Discover all available universes from sectors 88 and 70.

        Returns:
            dict mapping universe_key → (subsector_id, sector_number)
        """
        # Seed with known IDs for sector 88 (broad indices)
        result: dict[str, tuple[int | str, int]] = {
            k: (v, 88) for k, v in _KNOWN_IDS.items()
        }

        # Discover broad indices (sector 88)
        self._discover_sector(_SECTOR_88_URL, 88, _BROAD_NAME_HINTS, result)

        # Discover sectoral indices (sector 70)
        self._discover_sector(_SECTOR_70_URL, 70, _SECTORAL_NAME_HINTS, result)

        return result

    def _fetch_tickers(self, subsector_id: int | str, sector_num: int) -> list[str]:
        """Fetch all ticker symbols for a given subsector ID."""
        url = _COMPANY_URL.format(sector=sector_num, id=subsector_id)
        try:
            body = self._get(url)
            if not body:
                return []

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

    def list_available(self) -> dict[str, tuple[int | str, int]]:
        """Return the discovered universe_key → (subsector_id, sector_number) map.

        Runs discovery once and caches the result for the lifetime of this instance.
        """
        if self._subsector_map is None:
            self._subsector_map = self._discover_subsectors()
        return self._subsector_map

    def fetch(self, universe_key: str) -> list[str]:
        """Return sorted list of ticker symbols for the named universe.

        Args:
            universe_key: Any key from list_available() — broad (lq45, idx80, …)
                          or sectoral (finance, energy, health, …).

        Returns:
            Sorted list of ticker symbols, or [] if unavailable.
        """
        available = self.list_available()
        entry = available.get(universe_key.lower())
        if not entry:
            logger.warning("No subsector ID for universe '%s' — run discovery first", universe_key)
            return []

        subsector_id, sector_num = entry
        tickers = self._fetch_tickers(subsector_id, sector_num)
        logger.info("Universe '%s': %d tickers", universe_key, len(tickers))
        return tickers

    def fetch_universe_map(self) -> dict[str, int]:
        """Fetch universe ID map from /screener/universe in a single call.

        Returns:
            dict mapping canonical universe name (lowercased) → subsector_id.
            Empty dict on failure or unexpected response shape.

        Note: Response shape is unconfirmed — this probes and logs the result.
        Expected shape: {"data": [{"id": 550, "name": "LQ45", "sector_id": 88}, ...]}
        """
        try:
            body = self._get(_SCREENER_UNIVERSE_URL)
            if not body:
                logger.debug("Empty response from screener/universe")
                return {}
            data = body.get("data")
            if not isinstance(data, list):
                logger.info("screener/universe: unexpected shape — data is %s: %r", type(data).__name__, str(body)[:300])
                return {}
            result: dict[str, int] = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                sid = item.get("id")
                name = str(item.get("name") or "").strip()
                if sid is not None and name:
                    result[name.lower()] = int(sid)
            logger.info("screener/universe: found %d universes: %s", len(result), list(result.keys())[:10])
            return result
        except Exception as e:
            logger.warning("screener/universe fetch failed: %s", e)
            return {}

    def fetch_all(self, keys: list[str] | None = None) -> dict[str, list[str]]:
        """Fetch ticker lists for multiple universes.

        Args:
            keys: Universe keys to fetch. Defaults to all discovered universes.

        Returns:
            dict of universe_key → sorted ticker list (empty list on failure).
        """
        available = self.list_available()
        targets = keys if keys else list(available.keys())
        return {k: self.fetch(k) for k in targets}
