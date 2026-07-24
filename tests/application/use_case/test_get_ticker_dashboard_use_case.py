"""Unit tests for GetTickerDashboardUseCase with a fake source."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.application.dto.ticker_dashboard import GetTickerDashboardRequest
from src.application.ports.ticker_dashboard_source import TickerDashboardSource
from src.application.services.ticker_dashboard_status import CacheStatus
from src.application.use_case.get_ticker_dashboard_use_case import GetTickerDashboardUseCase
from src.domain.entities.broker_flow import ForeignFlowPoint
from src.domain.entities.candle import Candle
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from src.domain.value_objects.corporate_action_event import CorporateActionEvent
from src.domain.value_objects.earnings_record import EarningsRecord
from src.domain.value_objects.insider_transaction import InsiderTransaction


class FakeTickerDashboardSource(TickerDashboardSource):
    def __init__(self) -> None:
        self.notation = object()
        self.fundamentals = type("F", (), {"week52_high": 1500, "week52_low": 1000, "fetched_at": datetime(2026, 7, 20)})()
        self.analyst = type("A", (), {"fetched_at": datetime(2026, 7, 22)})()
        self.ownership = type("O", (), {"fetched_at": datetime(2026, 7, 21)})()
        self.bandar = type("B", (), {"session_date": date(2026, 7, 23)})()
        self.forward = object()
        self.profile = object()
        self.seasonality = object()
        self.corp_fresh = False
        self.candles = [
            Candle(
                ticker="BBCA",
                date=date(2026, 7, d),
                open=Decimal("1000"),
                high=Decimal("1010"),
                low=Decimal("990"),
                close=Decimal(str(1000 + d)),
                volume=1_000_000 + d * 1000,
            )
            for d in range(1, 24)
        ]
        self.ticker_corp: list[CorporateActionEvent] = []
        self.calendar_corp = [
            CorporateActionCalendarEvent(
                event_type=CorporateActionType.DIVIDEND,
                source_event_id="1",
                ticker="BBCA",
                dates=(
                    CorporateActionCalendarDate(CorporateActionDateRole.EX_DATE, date(2026, 6, 17)),
                    CorporateActionCalendarDate(CorporateActionDateRole.CUM_DATE, date(2026, 6, 15)),
                ),
                amount_value="20",
                amount_currency="CURRENCY_IDR",
                active=False,
            )
        ]
        self.insider_window: list[InsiderTransaction] = []
        self.insider_older = [
            InsiderTransaction(
                ticker="BBCA",
                name="X",
                role="DIREKTUR",
                action_type="BUY",
                shares=100,
                price=6000.0,
                # Outside the 12m dashboard window for today=2026-07-24.
                transaction_date=date(2025, 1, 15),
                ownership_before_pct=0.1,
                ownership_after_pct=0.11,
            )
        ]
        self.flow_stockbit = [
            ForeignFlowPoint(
                ticker="BBCA",
                date=date(2026, 7, 22),
                net_val=Decimal("100"),
                net_lot=1,
                avg_price=Decimal("6000"),
                source="stockbit",
            ),
            ForeignFlowPoint(
                ticker="BBCA",
                date=date(2026, 7, 23),
                net_val=Decimal("-50"),
                net_lot=-1,
                avg_price=Decimal("6100"),
                source="stockbit",
            ),
        ]
        self.flow_idx: list[ForeignFlowPoint] = []
        self.earnings = [
            EarningsRecord(
                ticker="BBCA",
                year=2026,
                quarter=1,
                eps_actual=119.1,
                eps_estimate=None,
                eps_surprise_pct=None,
                eps_yoy_change=3.8,
                eps_prev_year=114.7,
                fetched_at=datetime(2026, 7, 22),
            )
        ]
        self.iev = [type("I", (), {"date": date(2026, 7, 23)})()]
        self.sentiment = [object()]

    def get_notation(self, ticker: str) -> Any | None:
        return self.notation

    def get_fundamentals(self, ticker: str) -> Any | None:
        return self.fundamentals

    def get_analyst(self, ticker: str) -> Any | None:
        return self.analyst

    def get_ownership(self, ticker: str) -> Any | None:
        return self.ownership

    def get_bandar(self, ticker: str, session_date: date) -> Any | None:
        return self.bandar if session_date == date(2026, 7, 23) else None

    def get_forward_estimates(self, ticker: str) -> Any | None:
        return self.forward

    def get_profile(self, ticker: str) -> Any | None:
        return self.profile

    def get_candles(self, ticker: str, start_date: date, end_date: date) -> list[Candle]:
        return [c for c in self.candles if start_date <= c.date <= end_date]

    def get_ticker_corp_actions(self, ticker, from_date, to_date):
        return list(self.ticker_corp)

    def get_calendar_corp_actions(self, ticker, from_date, to_date):
        return list(self.calendar_corp)

    def is_ticker_corp_cache_fresh(self, ticker: str) -> bool:
        return self.corp_fresh

    def get_insider_transactions(self, ticker, from_date, to_date, action_type="ALL"):
        # Return any stored txns that fall inside the requested window.
        pool = list(self.insider_window) + list(self.insider_older)
        return [t for t in pool if from_date <= t.transaction_date <= to_date]

    def get_seasonality(self, ticker, year, month):
        return self.seasonality

    def get_foreign_flow_points(self, ticker, source):
        if source == "stockbit":
            return list(self.flow_stockbit)
        return list(self.flow_idx)

    def get_earnings_history(self, ticker, quarters):
        return list(self.earnings)[:quarters]

    def get_iev_history(self, ticker, limit):
        return list(self.iev)[:limit]

    def get_sentiment_logs(self, ticker, limit):
        return list(self.sentiment)[:limit]


def test_use_case_assembles_full_dashboard_with_policy():
    source = FakeTickerDashboardSource()
    uc = GetTickerDashboardUseCase(source)
    dash = uc.execute(
        GetTickerDashboardRequest(ticker="bbca", brief=False, today=date(2026, 7, 24))
    )

    assert dash.ticker == "BBCA"
    assert dash.mode == "full"
    assert dash.as_of == date(2026, 7, 23)
    assert dash.foreign_flow_source == "stockbit"
    assert len(dash.foreign_flow_points) == 2
    assert len(dash.corp_actions) == 1
    assert dash.corp_actions[0].detail == "Rp 20"
    assert dash.corp_status is CacheStatus.OK
    assert dash.insider_status is CacheStatus.EMPTY
    assert dash.insider_last_known == date(2025, 1, 15)
    assert dash.price_structure is not None
    assert dash.price_structure.close == Decimal("1023")
    assert "profile" in dash.panel_keys
    assert dash.fetch_hint == "saham fetch market BBCA"
    assert any(i.key == "price" and i.status is CacheStatus.OK for i in dash.freshness)
    assert dash.panel_errors == ()
    verbs = {a.verb for a in dash.related_actions}
    assert verbs == {"flow", "top-brokers", "foreign-history", "distribution"}
    assert all(dash.ticker in a.command for a in dash.related_actions)


def test_use_case_brief_mode_filters_panel_keys():
    source = FakeTickerDashboardSource()
    uc = GetTickerDashboardUseCase(source)
    dash = uc.execute(
        GetTickerDashboardRequest(ticker="BBCA", brief=True, today=date(2026, 7, 24))
    )
    assert dash.mode == "brief"
    assert "price_structure" in dash.panel_keys
    assert "foreign_flow" in dash.panel_keys
    assert "profile" not in dash.panel_keys
    assert "candles" not in dash.panel_keys


def test_use_case_isolates_panel_errors():
    source = FakeTickerDashboardSource()

    def boom(_ticker: str):
        raise RuntimeError("analyst cache exploded")

    source.get_analyst = boom  # type: ignore[method-assign]
    uc = GetTickerDashboardUseCase(source)
    dash = uc.execute(
        GetTickerDashboardRequest(ticker="BBCA", brief=False, today=date(2026, 7, 24))
    )
    assert dash.analyst is None
    assert any(e.key == "analyst" for e in dash.panel_errors)
    assert any(i.key == "analyst" and i.status is CacheStatus.ERROR for i in dash.freshness)
    # Other panels still load.
    assert dash.earnings
    assert dash.foreign_flow_points
