"""
SQLite/Stockbit-cache implementation of TickerDashboardSource.

Constructs cache-only providers (api_client=None) and exposes them behind the
application port. No network access.

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from src.application.ports.ticker_dashboard_source import TickerDashboardSource
from src.domain.entities.broker_flow import ForeignFlowPoint
from src.domain.entities.candle import Candle
from src.domain.value_objects.corporate_action_calendar import CorporateActionCalendarEvent
from src.domain.value_objects.corporate_action_event import CorporateActionEvent
from src.domain.value_objects.earnings_record import EarningsRecord
from src.domain.value_objects.insider_transaction import InsiderTransaction


class SQLiteTickerDashboardSource(TickerDashboardSource):
    """Local-cache ticker dashboard source over SQLite + Stockbit cache tables."""

    def __init__(self, db_path: Path | str) -> None:
        from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
        from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
        from src.infrastructure.browser.stockbit_company_profile import (
            StockbitCompanyProfileProvider,
        )
        from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
        from src.infrastructure.browser.stockbit_corp_action import (
            StockbitCorporateActionRepository,
        )
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
        from src.infrastructure.browser.stockbit_ticker_notation import (
            StockbitTickerNotationProvider,
        )
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
        common = dict(
            api_client=None,
            db_path=db,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        )

        self._notation = StockbitTickerNotationProvider(**common)
        self._fund = StockbitFundamentalsProvider(**common)
        self._analyst = StockbitAnalystConsensusProvider(**common)
        self._ownership = StockbitShareholdingProvider(**common)
        self._bandar = StockbitBandarDetectorProvider(**common)
        self._fwd = StockbitForwardEstimatesProvider(**common)
        self._profile = StockbitCompanyProfileProvider(**common)
        self._corp = StockbitCorporateActionRepository(**common)
        self._insider = StockbitInsiderActivityProvider(**common)
        self._seasonality = StockbitSeasonalityProvider(**common)
        self._earnings = StockbitEarningsProvider(**common)
        self._market = SQLiteMarketRepository(db)
        self._broker = SQLiteBrokerRepository(db)
        self._calendar = SQLiteCorporateActionCalendarRepository(db)
        self._iev = SQLiteIEVRepository(db)
        self._sentiment = SQLiteSentimentRepository(db)

    def get_notation(self, ticker: str) -> Any | None:
        return self._notation.read_cached(ticker)

    def get_fundamentals(self, ticker: str) -> Any | None:
        return self._fund.read_cached(ticker)

    def get_analyst(self, ticker: str) -> Any | None:
        return self._analyst.read_cached(ticker)

    def get_ownership(self, ticker: str) -> Any | None:
        return self._ownership.read_cached(ticker)

    def get_bandar(self, ticker: str, session_date: date) -> Any | None:
        return self._bandar.read_cached(ticker, session_date)

    def get_forward_estimates(self, ticker: str) -> Any | None:
        return self._fwd.read_cached(ticker)

    def get_profile(self, ticker: str) -> Any | None:
        return self._profile.read_cached(ticker)

    def get_candles(self, ticker: str, start_date: date, end_date: date) -> list[Candle]:
        return self._market.get_candles(ticker, start_date=start_date, end_date=end_date)

    def get_ticker_corp_actions(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[CorporateActionEvent]:
        return self._corp.read_cached(ticker, from_date, to_date)

    def get_calendar_corp_actions(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[CorporateActionCalendarEvent]:
        return self._calendar.get_events_for_ticker(ticker, from_date, to_date)

    def is_ticker_corp_cache_fresh(self, ticker: str) -> bool:
        try:
            return bool(self._corp.is_cache_fresh(ticker))
        except Exception:
            return False

    def get_insider_transactions(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str = "ALL",
    ) -> list[InsiderTransaction]:
        # Port method is already cache-capable when api_client=None.
        return self._insider.get_insider_transactions(ticker, from_date, to_date, action_type)

    def get_seasonality(self, ticker: str, year: int, month: int) -> Any | None:
        return self._seasonality.read_cached(ticker, year, month)

    def get_foreign_flow_points(self, ticker: str, source: str) -> list[ForeignFlowPoint]:
        return self._broker.get_foreign_flow_points(ticker, source=source)

    def get_earnings_history(self, ticker: str, quarters: int) -> list[EarningsRecord]:
        return self._earnings.get_earnings_history(ticker, quarters=quarters)

    def get_iev_history(self, ticker: str, limit: int) -> list[Any]:
        try:
            return self._iev.get_ticker_history(ticker, limit=limit)
        except Exception:
            return []

    def get_sentiment_logs(self, ticker: str, limit: int) -> list[Any]:
        try:
            return self._sentiment.get_ticker_logs(ticker, limit=limit)
        except Exception:
            return []
