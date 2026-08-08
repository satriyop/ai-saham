"""
Shared Playwright availability guard for Stockbit CLI commands.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.cli.cli_errors import raise_data_unavailable


def require_playwright_cli() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise_data_unavailable(
            "playwright not installed.",
            tip="Run: pip install playwright && playwright install chromium",
        )
