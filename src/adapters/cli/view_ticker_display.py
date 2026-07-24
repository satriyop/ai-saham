"""
show_ticker_view — read-only ticker information dashboard.

Reads all available SQLite-cached data for one ticker and renders it
as a series of Rich panels. Does NOT trigger any network fetch — callers
should run `saham fetch market TICKER` to populate/refresh caches.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from rich.text import Text

from src.adapters.cli.rich_display import console
from src.adapters.cli.view_ticker_events_display import (
    CORP_ACTION_LOOKAHEAD_DAYS,
    CORP_ACTION_LOOKBACK_DAYS,
    _calendar_event_to_display,
    _corp_action_panel,
    _merge_corp_action_events,
    _sentiment_panel,
)
from src.adapters.cli.view_ticker_flow_display import (
    INSIDER_LOOKBACK_DAYS,
    _bandar_panel,
    _insider_panel,
)
from src.adapters.cli.view_ticker_identity_display import _identity_panel, _profile_panel
from src.adapters.cli.view_ticker_market_activity_display import (
    _candles_panel,
    _iev_panel,
    _seasonality_panel,
)
from src.adapters.cli.view_ticker_valuation_display import (
    _analyst_panel,
    _ownership_panel,
    _valuation_panel,
)

DEFAULT_DB_PATH = Path("data.db")


def show_ticker_view(ticker: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Render a read-only dashboard of all cached data for ticker."""
    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_company_profile import StockbitCompanyProfileProvider
    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )
    from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
    from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
        StockbitSQLiteConnectionProvider,
    )
    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
    from src.infrastructure.persistence.sentiment_repository import SQLiteSentimentRepository
    from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
        SQLiteCorporateActionCalendarRepository,
    )
    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
    from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

    db = Path(db_path)
    connection_provider = StockbitSQLiteConnectionProvider()
    stockbit_config = load_stockbit_provider_config()

    notation_prov = StockbitTickerNotationProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    fund_prov = StockbitFundamentalsProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    analyst_prov = StockbitAnalystConsensusProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    sh_prov = StockbitShareholdingProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    bandar_prov = StockbitBandarDetectorProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    fwd_prov = StockbitForwardEstimatesProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    profile_prov = StockbitCompanyProfileProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    corp_action_repo = StockbitCorporateActionRepository(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    insider_prov = StockbitInsiderActivityProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    seasonality_prov = StockbitSeasonalityProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    market_repo = SQLiteMarketRepository(db)
    calendar_repo = SQLiteCorporateActionCalendarRepository(db)
    iev_repo = SQLiteIEVRepository(db)
    sentiment_repo = SQLiteSentimentRepository(db)

    today = date.today()
    corp_from = today - timedelta(CORP_ACTION_LOOKBACK_DAYS)
    corp_to = today + timedelta(CORP_ACTION_LOOKAHEAD_DAYS)
    insider_from = today - timedelta(INSIDER_LOOKBACK_DAYS)

    notation = notation_prov._read_cache(ticker)
    fund = fund_prov._read_cache(ticker)
    analyst = analyst_prov._read_cache(ticker)
    sh = sh_prov._read_cache(ticker)
    bandar = bandar_prov._read_cache(ticker, today) or bandar_prov._read_cache(
        ticker, today - timedelta(1)
    )
    fwd = fwd_prov._read_cache(ticker)
    profile = profile_prov._read_cache(ticker)
    candles = market_repo.get_candles(ticker, start_date=today - timedelta(14), end_date=today)

    # Prefer showing events that already happened (history), not only a short
    # forward window. Merge ticker-level cache with market-wide calendar store.
    ticker_corp_actions = corp_action_repo._read_cache(ticker, corp_from, corp_to)
    calendar_corp_actions = [
        _calendar_event_to_display(event)
        for event in calendar_repo.get_events_for_ticker(ticker, corp_from, corp_to)
    ]
    corp_actions = _merge_corp_action_events(ticker_corp_actions, calendar_corp_actions)

    # Insider cache is owned by StockbitInsiderCache; use the port method
    # (api_client=None keeps this cache-only / no network).
    insider_txns = insider_prov.get_insider_transactions(
        ticker, insider_from, today, "ALL"
    )
    seasonality = seasonality_prov._read_cache(ticker, today.year, today.month)

    # IEV: retrieve using repository
    iev_rows: list = []
    try:
        iev_rows = iev_repo.get_ticker_history(ticker, limit=5)
    except Exception:
        pass

    # Sentiment: retrieve using repository
    sentiment_logs: list = []
    try:
        sentiment_logs = sentiment_repo.get_ticker_logs(ticker, limit=8)
    except Exception:
        pass

    latest_close = candles[-1].close if candles else None

    c = console()
    c.print()
    c.print(_identity_panel(ticker, notation))
    c.print(_valuation_panel(fund, fwd, latest_close))
    c.print(_analyst_panel(analyst))
    c.print(_ownership_panel(sh))
    c.print(_bandar_panel(bandar))
    c.print(_corp_action_panel(corp_actions))
    c.print(_insider_panel(insider_txns))
    c.print(_seasonality_panel(seasonality, today.month))
    c.print(_iev_panel(iev_rows))
    c.print(_sentiment_panel(sentiment_logs))
    c.print(_profile_panel(profile))
    c.print(_candles_panel(candles))
    c.print(
        Text(f"  Run `saham fetch market {ticker}` to refresh stale or missing data.", style="dim")
    )
    c.print()
