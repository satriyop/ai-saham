"""
Port: TickerDashboardSource

Cache-only data access for the ticker dashboard use case.
Implementations must not trigger network fetches.

Layer: Application (port definition)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from src.domain.entities.broker_flow import ForeignFlowPoint
from src.domain.entities.candle import Candle
from src.domain.value_objects.corporate_action_calendar import CorporateActionCalendarEvent
from src.domain.value_objects.corporate_action_event import CorporateActionEvent
from src.domain.value_objects.earnings_record import EarningsRecord
from src.domain.value_objects.insider_transaction import InsiderTransaction


class TickerDashboardSource(ABC):
    """Read-only local data source for one-ticker dashboard assembly."""

    @abstractmethod
    def get_notation(self, ticker: str) -> Any | None: ...

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> Any | None: ...

    @abstractmethod
    def get_analyst(self, ticker: str) -> Any | None: ...

    @abstractmethod
    def get_ownership(self, ticker: str) -> Any | None: ...

    @abstractmethod
    def get_bandar(self, ticker: str, session_date: date) -> Any | None: ...

    @abstractmethod
    def get_forward_estimates(self, ticker: str) -> Any | None: ...

    @abstractmethod
    def get_profile(self, ticker: str) -> Any | None: ...

    @abstractmethod
    def get_candles(self, ticker: str, start_date: date, end_date: date) -> list[Candle]: ...

    @abstractmethod
    def get_ticker_corp_actions(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[CorporateActionEvent]: ...

    @abstractmethod
    def get_calendar_corp_actions(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[CorporateActionCalendarEvent]: ...

    @abstractmethod
    def is_ticker_corp_cache_fresh(self, ticker: str) -> bool: ...

    @abstractmethod
    def get_insider_transactions(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str = "ALL",
    ) -> list[InsiderTransaction]: ...

    @abstractmethod
    def get_seasonality(self, ticker: str, year: int, month: int) -> Any | None: ...

    @abstractmethod
    def get_foreign_flow_points(
        self, ticker: str, source: str
    ) -> list[ForeignFlowPoint]: ...

    @abstractmethod
    def get_earnings_history(
        self, ticker: str, quarters: int
    ) -> list[EarningsRecord]: ...

    @abstractmethod
    def get_iev_history(self, ticker: str, limit: int) -> list[Any]: ...

    @abstractmethod
    def get_sentiment_logs(self, ticker: str, limit: int) -> list[Any]: ...
