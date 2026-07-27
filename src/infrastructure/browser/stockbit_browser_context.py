"""
Stockbit browser context lifecycle and configuration constants.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.infrastructure.config.app_config import AppConfig, load_app_config

logger = logging.getLogger(__name__)


# ── Defaults ───────────────────────────────────────────────────────────────
def default_stockbit_profile_dir(config: AppConfig | None = None) -> Path:
    cfg = config or load_app_config()
    return Path(cfg.storage.stockbit_profile_dir)


# ── Stockbit URLs (hardcoded — not from StockbitConfig) ────────────────────
BASE_URL = "https://stockbit.com"
STREAM_URL = "https://stockbit.com/stream"
SCREENER_URL = "https://stockbit.com/screener"
ORDER_BOOK_URL = "https://stockbit.com/stock/{ticker}/orderbook"
ORDERBOOK_PAGE_URL = "https://stockbit.com/orderbook"
LOGIN_URL = "https://stockbit.com/login"


def _require_playwright():
    """Import playwright or raise with install instructions."""
    try:
        from playwright.sync_api import sync_playwright

        return sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed. Run:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )


def _persistent_context(pw, profile_dir: Path, headless: bool = True):
    """
    Launch a persistent Chromium context using a saved browser profile.

    The profile directory stores ALL browser state (cookies, localStorage,
    IndexedDB, cache) exactly like a real Chrome profile.

    Returns:
        (context, page) — context IS the browser; call context.close() when done.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        args=["--no-first-run", "--no-default-browser-check"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page
