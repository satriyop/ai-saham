"""Unit tests for ticker dashboard JSON serialization from DTO."""

from datetime import date, datetime
from decimal import Decimal

from src.adapters.cli.view_ticker_json import ticker_dashboard_to_json_dict
from src.application.dto.ticker_dashboard import TickerDashboard
from src.application.services.ticker_dashboard_layout import panel_keys_for_mode
from src.application.services.ticker_dashboard_price_structure import PriceStructure
from src.application.services.ticker_dashboard_status import CacheStatus, FreshnessItem
from src.domain.entities.broker_flow import ForeignFlowPoint
from src.domain.entities.candle import Candle
from src.domain.value_objects.earnings_record import EarningsRecord


def _candle(day: int, close: str) -> Candle:
    c = Decimal(close)
    return Candle(
        ticker="BBCA",
        date=date(2026, 7, day),
        open=c,
        high=c,
        low=c,
        close=c,
        volume=1_000_000,
    )


def _dashboard(*, brief: bool) -> TickerDashboard:
    structure = PriceStructure(
        as_of=date(2026, 7, 23),
        close=Decimal("6275"),
        change_1d_pct=-3.5,
        change_5d_pct=0.8,
        change_20d_pct=4.1,
        high_52w=Decimal("8975"),
        low_52w=Decimal("4820"),
        range_52w_pct=35.0,
        volume=207_000_000,
        avg_volume_20d=187_700_000.0,
        volume_vs_20d=1.1,
    )
    freshness = (
        FreshnessItem("price", "Price", CacheStatus.OK, as_of=date(2026, 7, 23), age_days=1),
        FreshnessItem("flow", "Flow", CacheStatus.MISSING),
    )
    flow = (
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
    )
    earnings = (
        EarningsRecord(
            ticker="BBCA",
            year=2026,
            quarter=1,
            eps_actual=119.1,
            eps_estimate=None,
            eps_surprise_pct=None,
            eps_yoy_change=3.8,
            eps_prev_year=114.7,
            fetched_at=datetime(2026, 7, 22, 6, 0, 0),
        ),
    )
    candles = (_candle(21, "6400"), _candle(22, "6500"), _candle(23, "6275"))
    return TickerDashboard(
        ticker="BBCA",
        mode="brief" if brief else "full",
        as_of=date(2026, 7, 23),
        today=date(2026, 7, 24),
        fetch_hint="saham fetch market BBCA",
        panel_keys=panel_keys_for_mode(brief=brief),
        freshness=freshness,
        notation=None,
        fundamentals=None,
        forward_estimates=None,
        latest_close=Decimal("6275"),
        price_structure=structure,
        analyst=None,
        earnings=earnings,
        ownership=None,
        bandar=None,
        foreign_flow_points=flow,
        foreign_flow_source="stockbit",
        corp_actions=(),
        corp_status=CacheStatus.EMPTY,
        insider_txns=(),
        insider_status=CacheStatus.EMPTY,
        insider_last_known=date(2026, 3, 25),
        seasonality=None,
        iev_rows=(),
        sentiment_logs=(),
        profile=None,
        candles=candles,
    )


def test_ticker_dashboard_to_json_dict_full_and_brief():
    full = ticker_dashboard_to_json_dict(_dashboard(brief=False))
    assert full["ticker"] == "BBCA"
    assert full["mode"] == "full"
    assert "profile" in full["panels"]
    assert full["data"]["price_structure"]["close"] == "6275"
    assert full["data"]["foreign_flow"]["source"] == "stockbit"
    assert full["data"]["foreign_flow"]["latest"]["net_val"] == "-50"
    assert full["data"]["earnings"][0]["period_label"] == "Q1 2026"
    assert full["data"]["insider"]["last_known_outside_window"] == "2026-03-25"
    assert len(full["data"]["candles"]) == 3

    brief = ticker_dashboard_to_json_dict(_dashboard(brief=True))
    assert brief["mode"] == "brief"
    assert "price_structure" in brief["data"]
    assert "foreign_flow" in brief["data"]
    assert "profile" not in brief["data"]
    assert "candles" not in brief["data"]
    assert "ownership" not in brief["data"]
