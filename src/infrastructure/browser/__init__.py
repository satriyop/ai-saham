"""Browser data infrastructure — adapters for browser-sourced market data."""

from src.infrastructure.browser.stockbit_browser_provider import (
    ManualBrowserDataProvider,
    StockbitBrowserInstructionsProvider,
)

__all__ = [
    "ManualBrowserDataProvider",
    "StockbitBrowserInstructionsProvider",
]
