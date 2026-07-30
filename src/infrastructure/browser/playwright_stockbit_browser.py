"""
Playwright browser session utilities for Stockbit.

Compatibility facade. Re-exports symbols from stockbit_browser_context,
stockbit_token_extractor, and stockbit_session_actions.

Layer: Infrastructure
"""

from __future__ import annotations

# Re-export from stockbit_api_client
from src.infrastructure.browser.stockbit_api_client import (
    StockbitSessionExpired as StockbitSessionExpired,
)

# Re-export from stockbit_browser_context
from src.infrastructure.browser.stockbit_browser_context import (
    BASE_URL as BASE_URL,
)
from src.infrastructure.browser.stockbit_browser_context import (
    LOGIN_URL as LOGIN_URL,
)
from src.infrastructure.browser.stockbit_browser_context import (
    ORDER_BOOK_URL as ORDER_BOOK_URL,
)
from src.infrastructure.browser.stockbit_browser_context import (
    ORDERBOOK_PAGE_URL as ORDERBOOK_PAGE_URL,
)
from src.infrastructure.browser.stockbit_browser_context import (
    SCREENER_URL as SCREENER_URL,
)
from src.infrastructure.browser.stockbit_browser_context import (
    STREAM_URL as STREAM_URL,
)
from src.infrastructure.browser.stockbit_browser_context import (
    _persistent_context as _persistent_context,
)
from src.infrastructure.browser.stockbit_browser_context import (
    _require_playwright as _require_playwright,
)
from src.infrastructure.browser.stockbit_browser_context import (
    default_stockbit_profile_dir as default_stockbit_profile_dir,
)

# Re-export from stockbit_session_actions
from src.infrastructure.browser.stockbit_session_actions import (
    _persist_newer_token as _persist_newer_token,
)
from src.infrastructure.browser.stockbit_session_actions import (
    browse_stockbit_session as browse_stockbit_session,
)
from src.infrastructure.browser.stockbit_session_actions import (
    get_stockbit_session_status as get_stockbit_session_status,
)
from src.infrastructure.browser.stockbit_session_actions import (
    reauth_stockbit_session as reauth_stockbit_session,
)
from src.infrastructure.browser.stockbit_session_actions import (
    save_stockbit_session as save_stockbit_session,
)
from src.infrastructure.browser.stockbit_session_actions import (
    spy_stockbit_session as spy_stockbit_session,
)

# Re-export from stockbit_token_extractor
from src.infrastructure.browser.stockbit_token_extractor import (
    _extract_jwt as _extract_jwt,
)
from src.infrastructure.browser.stockbit_token_extractor import (
    _intercept_token as _intercept_token,
)
from src.infrastructure.browser.stockbit_token_extractor import (
    _resolve_token as _resolve_token,
)
from src.infrastructure.browser.stockbit_token_extractor import (
    extract_exodus_token as extract_exodus_token,
)
