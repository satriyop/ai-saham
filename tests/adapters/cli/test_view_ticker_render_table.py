"""Unit tests for pure table rendering over TickerDashboard DTO."""

from datetime import date

from src.adapters.cli.view_ticker_display import _render_ticker_dashboard_table
from src.application.dto.ticker_dashboard import TickerDashboard
from src.application.services.ticker_dashboard_layout import panel_keys_for_mode
from src.application.services.ticker_dashboard_status import CacheStatus, FreshnessItem


def _empty_dashboard(*, brief: bool) -> TickerDashboard:
    return TickerDashboard(
        ticker="BBCA",
        mode="brief" if brief else "full",
        as_of=date(2026, 7, 23),
        today=date(2026, 7, 24),
        fetch_hint="saham fetch market BBCA",
        panel_keys=panel_keys_for_mode(brief=brief),
        freshness=(
            FreshnessItem("price", "Price", CacheStatus.MISSING),
            FreshnessItem("flow", "Flow", CacheStatus.MISSING),
        ),
        related_actions=(),
        panel_errors=(),
        notation=None,
        fundamentals=None,
        forward_estimates=None,
        latest_close=None,
        price_structure=None,
        analyst=None,
        earnings=(),
        ownership=None,
        bandar=None,
        foreign_flow_points=(),
        foreign_flow_source=None,
        corp_actions=(),
        corp_status=CacheStatus.MISSING,
        insider_txns=(),
        insider_status=CacheStatus.MISSING,
        insider_last_known=None,
        seasonality=None,
        iev_rows=(),
        sentiment_logs=(),
        profile=None,
        candles=(),
    )


def test_render_table_brief_does_not_raise():
    # Smoke: pure renderer accepts DTO and prints without loading providers.
    _render_ticker_dashboard_table(_empty_dashboard(brief=True))


def test_render_table_full_does_not_raise():
    _render_ticker_dashboard_table(_empty_dashboard(brief=False))
