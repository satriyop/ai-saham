"""
Ticker dashboard DTOs — read-only local-cache snapshot for one ticker.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from src.application.services.ticker_dashboard_price_structure import PriceStructure
from src.application.services.ticker_dashboard_status import CacheStatus, FreshnessItem
from src.domain.entities.broker_flow import ForeignFlowPoint
from src.domain.entities.candle import Candle
from src.domain.value_objects.corporate_action_event import CorporateActionEvent
from src.domain.value_objects.earnings_record import EarningsRecord
from src.domain.value_objects.insider_transaction import InsiderTransaction


@dataclass(frozen=True)
class GetTickerDashboardRequest:
    """Request for a cache-only ticker dashboard snapshot."""

    ticker: str
    brief: bool = False
    today: date | None = None  # injectable for tests; defaults to date.today()


@dataclass(frozen=True)
class ViewRelatedAction:
    """Structured deep-dive link for CLI footer / future TUI tabs."""

    verb: str
    label: str
    command: str


@dataclass(frozen=True)
class PanelLoadError:
    """Isolated panel failure that should not abort the whole dashboard."""

    key: str
    message: str


@dataclass(frozen=True)
class TickerDashboard:
    """Assembled local-cache dashboard for one ticker.

    Contains raw panel payloads plus policy outputs (freshness, statuses,
    selected panel keys). Adapters only format this object.
    """

    ticker: str
    mode: str  # "full" | "brief"
    as_of: date | None
    today: date
    fetch_hint: str
    panel_keys: tuple[str, ...]
    freshness: tuple[FreshnessItem, ...]
    related_actions: tuple[ViewRelatedAction, ...]
    panel_errors: tuple[PanelLoadError, ...]

    notation: Any | None
    fundamentals: Any | None
    forward_estimates: Any | None
    latest_close: Decimal | None
    price_structure: PriceStructure | None
    analyst: Any | None
    earnings: tuple[EarningsRecord, ...]
    ownership: Any | None
    bandar: Any | None
    foreign_flow_points: tuple[ForeignFlowPoint, ...]
    foreign_flow_source: str | None
    corp_actions: tuple[CorporateActionEvent, ...]
    corp_status: CacheStatus
    insider_txns: tuple[InsiderTransaction, ...]
    insider_status: CacheStatus
    insider_last_known: date | None
    seasonality: Any | None
    iev_rows: tuple[Any, ...]
    sentiment_logs: tuple[Any, ...]
    profile: Any | None
    candles: tuple[Candle, ...]
