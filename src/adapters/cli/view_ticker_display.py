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
    FOREIGN_FLOW_SOURCE_PREFERENCE,
    INSIDER_LOOKBACK_DAYS,
    _bandar_panel,
    _foreign_flow_panel,
    _insider_panel,
    _select_foreign_flow_points,
)
from src.adapters.cli.view_ticker_identity_display import (
    _freshness_panel,
    _identity_panel,
    _profile_panel,
)
from src.adapters.cli.view_ticker_market_activity_display import (
    _candles_panel,
    _iev_panel,
    _price_structure_panel,
    _seasonality_panel,
)
from src.adapters.cli.view_ticker_price_structure import compute_price_structure
from src.adapters.cli.view_ticker_status import (
    DEFAULT_TTL_DAYS,
    build_freshness_item,
    classify_optional,
    classify_sequence,
    default_fetch_hint,
)
from src.adapters.cli.view_ticker_valuation_display import (
    EARNINGS_QUARTERS,
    _analyst_panel,
    _earnings_panel,
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
    from src.infrastructure.browser.stockbit_earnings import StockbitEarningsProvider
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
    from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
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
    earnings_prov = StockbitEarningsProvider(
        api_client=None,
        db_path=db,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    market_repo = SQLiteMarketRepository(db)
    broker_repo = SQLiteBrokerRepository(db)
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
    # Need ~20 sessions for structure + recent strip; pull a wide local window.
    candles = market_repo.get_candles(
        ticker, start_date=today - timedelta(days=400), end_date=today
    )

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
    insider_last_known = None
    if not insider_txns:
        older_insider = insider_prov.get_insider_transactions(
            ticker, today - timedelta(days=3650), insider_from - timedelta(days=1), "ALL"
        )
        if older_insider:
            insider_last_known = older_insider[0].transaction_date
    seasonality = seasonality_prov._read_cache(ticker, today.year, today.month)

    # Foreign flow: prefer a single source so multi-day nets stay coherent.
    flow_by_source = {
        source: broker_repo.get_foreign_flow_points(ticker, source=source)
        for source in FOREIGN_FLOW_SOURCE_PREFERENCE
    }
    foreign_flow_points, foreign_flow_source = _select_foreign_flow_points(flow_by_source)

    # Earnings: port method with api_client=None stays cache-only.
    earnings = earnings_prov.get_earnings_history(ticker, quarters=EARNINGS_QUARTERS)

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
    price_structure = compute_price_structure(
        candles,
        week52_high=getattr(fund, "week52_high", None) if fund is not None else None,
        week52_low=getattr(fund, "week52_low", None) if fund is not None else None,
    )
    fetch_hint = default_fetch_hint(ticker)

    price_as_of = candles[-1].date if candles else None
    flow_as_of = foreign_flow_points[-1].date if foreign_flow_points else None
    bandar_as_of = getattr(bandar, "session_date", None) if bandar is not None else None
    fund_as_of = getattr(fund, "fetched_at", None) if fund is not None else None
    analyst_as_of = getattr(analyst, "fetched_at", None) if analyst is not None else None
    earnings_as_of = earnings[0].fetched_at if earnings else None
    ownership_as_of = getattr(sh, "fetched_at", None) if sh is not None else None
    iev_as_of = iev_rows[0].date if iev_rows else None
    # Event-history panels are OK/EMPTY/MISSING only — old event dates are not
    # "stale cache", they are historical facts still worth showing.
    insider_status = classify_sequence(
        insider_txns,
        ever_fetched=insider_last_known is not None,
        last_known=insider_last_known,
    )
    corp_status = classify_sequence(
        corp_actions,
        ever_fetched=bool(ticker_corp_actions) or bool(calendar_corp_actions),
    )
    # If calendar/ticker raw produced nothing but a ticker __NONE__ may still mean fetched.
    if not corp_actions:
        try:
            if corp_action_repo._is_cache_fresh(ticker):
                corp_status = classify_sequence([], ever_fetched=True)
        except Exception:
            pass

    freshness_items = [
        build_freshness_item(
            "price",
            "Price",
            classify_sequence(candles, as_of=price_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["price"]),
            as_of=price_as_of,
            today=today,
        ),
        build_freshness_item(
            "flow",
            "Flow",
            classify_sequence(
                foreign_flow_points,
                as_of=flow_as_of,
                today=today,
                ttl_days=DEFAULT_TTL_DAYS["flow"],
            ),
            as_of=flow_as_of,
            today=today,
        ),
        build_freshness_item(
            "bandar",
            "Bandar",
            classify_optional(
                bandar, as_of=bandar_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["bandar"]
            ),
            as_of=bandar_as_of,
            today=today,
        ),
        build_freshness_item(
            "earnings",
            "Earnings",
            classify_sequence(
                earnings,
                as_of=earnings_as_of,
                today=today,
                ttl_days=DEFAULT_TTL_DAYS["earnings"],
            ),
            as_of=earnings_as_of,
            today=today,
        ),
        build_freshness_item(
            "analyst",
            "Analyst",
            classify_optional(
                analyst, as_of=analyst_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["analyst"]
            ),
            as_of=analyst_as_of,
            today=today,
        ),
        build_freshness_item(
            "fundamentals",
            "Fundamentals",
            classify_optional(
                fund, as_of=fund_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["fundamentals"]
            ),
            as_of=fund_as_of,
            today=today,
        ),
        build_freshness_item(
            "ownership",
            "Ownership",
            classify_optional(
                sh, as_of=ownership_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["ownership"]
            ),
            as_of=ownership_as_of,
            today=today,
        ),
        build_freshness_item(
            "insider",
            "Insider",
            insider_status,
            as_of=insider_txns[0].transaction_date if insider_txns else insider_last_known,
            today=today,
        ),
        build_freshness_item(
            "corp",
            "Corp",
            corp_status,
            today=today,
        ),
        build_freshness_item(
            "iev",
            "IEV",
            classify_sequence(iev_rows, as_of=iev_as_of, today=today, ttl_days=DEFAULT_TTL_DAYS["iev"]),
            as_of=iev_as_of,
            today=today,
        ),
    ]
    dashboard_as_of = price_as_of or flow_as_of or today

    c = console()
    c.print()
    c.print(_identity_panel(ticker, notation, empty_hint=fetch_hint))
    c.print(_freshness_panel(ticker, freshness_items, as_of=dashboard_as_of))
    c.print(_valuation_panel(fund, fwd, latest_close))
    c.print(_price_structure_panel(price_structure, empty_hint=fetch_hint))
    c.print(_analyst_panel(analyst, empty_hint=fetch_hint))
    c.print(_earnings_panel(earnings, empty_hint=fetch_hint))
    c.print(_ownership_panel(sh, empty_hint=fetch_hint))
    c.print(_bandar_panel(bandar, empty_hint=fetch_hint))
    c.print(
        _foreign_flow_panel(
            foreign_flow_points, source=foreign_flow_source, empty_hint=fetch_hint
        )
    )
    c.print(
        _corp_action_panel(
            corp_actions,
            status=corp_status,
            empty_hint=fetch_hint,
        )
    )
    c.print(
        _insider_panel(
            insider_txns,
            status=insider_status,
            last_known=insider_last_known,
            empty_hint=fetch_hint,
        )
    )
    c.print(_seasonality_panel(seasonality, today.month, empty_hint=fetch_hint))
    c.print(_iev_panel(iev_rows, empty_hint=fetch_hint))
    c.print(_sentiment_panel(sentiment_logs, empty_hint=fetch_hint))
    c.print(_profile_panel(profile, empty_hint=fetch_hint))
    c.print(_candles_panel(candles, empty_hint=fetch_hint))
    c.print(
        Text(f"  Run `{fetch_hint}` to refresh stale or missing data.", style="dim")
    )
    c.print()
