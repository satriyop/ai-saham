"""
Playwright-based Stockbit browser provider.

Automates Stockbit navigation using a saved browser session (cookie injection).
No username/password stored — session cookies are captured once via
`saham screen save-session` and reused on subsequent runs.

When playwright is not installed, this module gracefully errors with a helpful message.

Flow:
  1. saham screen save-session  → launches headed Chromium, user logs in, cookies saved
  2. saham screen pre-open      → loads cookies into headless Playwright, auto-scrapes

Layer: Infrastructure
Depends on: playwright (optional), BrowserDataProvider port
"""

from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from pathlib import Path

from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.value_objects.screener_result import MoverData, OrderBookBid

logger = logging.getLogger(__name__)

DEFAULT_SESSION_FILE = Path("stockbit_session.json")

# Stockbit URLs
SCREENER_URL = "https://stockbit.com/#/screener"
ORDER_BOOK_URL = "https://stockbit.com/#/stock/{ticker}/orderbook"

# Timeouts (ms)
NAV_TIMEOUT = 30_000
ELEMENT_TIMEOUT = 15_000


def _require_playwright():
    """Import playwright.sync_api or raise with install instructions."""
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed. Run:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )


class PlaywrightStockbitProvider(BrowserDataProvider):
    """
    Fully autonomous Stockbit browser provider using Playwright.

    Loads cookies from a saved session file to authenticate. No username/password
    is stored anywhere — only browser session cookies.

    Usage:
        provider = PlaywrightStockbitProvider(headless=True)
        movers = provider.fetch_preopen_movers(iev_min=100_000)
        ob = provider.fetch_order_book_best_bid("BBCA")
    """

    def __init__(
        self,
        session_file: Path = DEFAULT_SESSION_FILE,
        headless: bool = True,
        timeout: int = NAV_TIMEOUT,
    ) -> None:
        self._session_file = session_file
        self._headless = headless
        self._timeout = timeout

    def _load_cookies(self) -> list[dict]:
        """Load cookies from the session file."""
        if not self._session_file.exists():
            raise RuntimeError(
                f"No session file at '{self._session_file}'. "
                "Run: saham screen save-session"
            )
        with open(self._session_file) as f:
            data = json.load(f)
        return data.get("cookies", [])

    def fetch_preopen_movers(self, iev_min: int) -> list[MoverData]:
        """
        Navigate Stockbit screener, extract movers with IEV >= iev_min.

        Args:
            iev_min: Minimum IEV threshold to filter movers

        Returns:
            List of MoverData sorted by IEV descending
        """
        sync_playwright = _require_playwright()
        cookies = self._load_cookies()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self._headless)
            ctx = browser.new_context()
            ctx.add_cookies(cookies)
            page = ctx.new_page()

            try:
                page.goto(SCREENER_URL, timeout=self._timeout)
                # Wait for the movers table to load
                page.wait_for_selector("table", timeout=ELEMENT_TIMEOUT)

                # Look for "Selengkapnya" button in Movers section and click it
                try:
                    see_more = page.locator("text=Selengkapnya").first
                    if see_more.is_visible():
                        see_more.click()
                        time.sleep(1)
                except Exception:
                    pass

                # Extract rows from the movers table
                # Stockbit renders IEV as formatted numbers in the table
                movers: list[MoverData] = []
                rows = page.query_selector_all("table tbody tr")

                for row in rows:
                    cells = row.query_selector_all("td")
                    if len(cells) < 2:
                        continue
                    try:
                        ticker = cells[0].inner_text().strip().upper()
                        iev_text = cells[-1].inner_text().strip().replace(",", "").replace(".", "")
                        iev = int(iev_text)
                        if iev >= iev_min and ticker:
                            movers.append(MoverData(ticker=ticker, iev=iev))
                    except (ValueError, IndexError):
                        continue

                logger.info("Playwright: fetched %d movers with IEV >= %d", len(movers), iev_min)
                return sorted(movers, key=lambda m: m.iev, reverse=True)

            finally:
                browser.close()

    def fetch_order_book_best_bid(self, ticker: str) -> OrderBookBid | None:
        """
        Navigate Stockbit order book, return the largest bid (by volume).

        Args:
            ticker: IDX ticker symbol (e.g., "BBCA")

        Returns:
            OrderBookBid with price and volume of the largest bid, or None
        """
        sync_playwright = _require_playwright()
        cookies = self._load_cookies()
        url = ORDER_BOOK_URL.format(ticker=ticker.upper())

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self._headless)
            ctx = browser.new_context()
            ctx.add_cookies(cookies)
            page = ctx.new_page()

            try:
                page.goto(url, timeout=self._timeout)
                page.wait_for_selector("table", timeout=ELEMENT_TIMEOUT)

                # Find the bid side table (typically labeled "BID" or left column)
                best_price: Decimal | None = None
                best_volume: int = 0

                rows = page.query_selector_all("table tbody tr")
                for row in rows:
                    cells = row.query_selector_all("td")
                    if len(cells) < 2:
                        continue
                    try:
                        price_text = cells[0].inner_text().strip().replace(",", "").replace(".", "")
                        vol_text = cells[1].inner_text().strip().replace(",", "").replace(".", "")
                        price = Decimal(price_text)
                        volume = int(vol_text)
                        if volume > best_volume:
                            best_price = price
                            best_volume = volume
                    except (ValueError, IndexError):
                        continue

                if best_price is not None:
                    logger.info(
                        "Playwright: %s best bid price=%s vol=%d", ticker, best_price, best_volume
                    )
                    return OrderBookBid(price=best_price, volume=best_volume)
                return None

            finally:
                browser.close()


def save_stockbit_session(
    session_file: Path = DEFAULT_SESSION_FILE,
    timeout: int = 120,
) -> None:
    """
    Launch a headed Chromium browser for the user to log into Stockbit manually.
    Cookies are saved to session_file for subsequent headless runs.

    Args:
        session_file: Path to write cookies JSON
        timeout: Seconds to wait for user to complete login
    """
    sync_playwright = _require_playwright()

    print("Opening Stockbit in a browser window. Please log in manually.")
    print(f"You have {timeout} seconds. The window will close automatically.")
    print(f"Session will be saved to: {session_file}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://stockbit.com/#/login", timeout=NAV_TIMEOUT)

        # Poll until the user is logged in (dashboard appears) or timeout
        start = time.time()
        logged_in = False
        while time.time() - start < timeout:
            try:
                # Stockbit dashboard has a sidebar nav — check for a nav element
                if page.url and "login" not in page.url.lower():
                    logged_in = True
                    break
            except Exception:
                pass
            time.sleep(2)

        if logged_in:
            cookies = ctx.cookies()
            session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(session_file, "w") as f:
                json.dump({"cookies": cookies}, f, indent=2)
            print(f"\nSession saved to {session_file}")
            print("Run 'saham screen pre-open' to start the screener.")
        else:
            print("\nTimeout — login not detected. Session NOT saved.")
            print("Run 'saham screen save-session' again and log in within the time limit.")

        browser.close()
