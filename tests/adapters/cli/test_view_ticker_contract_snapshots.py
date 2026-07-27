"""Snapshot-style contract tests for view ticker JSON shapes."""

from datetime import date
from decimal import Decimal

from src.adapters.cli.view_ticker_json import ticker_dashboard_to_json_dict
from src.application.dto.ticker_dashboard import (
    TickerDashboard,
    ViewRelatedAction,
)
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewWindow,
    build_view_envelope,
)
from src.application.services.ticker_dashboard_layout import panel_keys_for_mode
from src.application.services.ticker_dashboard_status import CacheStatus, FreshnessItem

ENVELOPE_KEYS = {
    "subject",
    "verb",
    "as_of",
    "window",
    "source",
    "scope",
    "scope_note",
    "status",
    "fetch_hint",
    "data",
}


def test_deep_dive_and_show_share_envelope_keys():
    deep = build_view_envelope(
        subject_id="BBCA",
        verb="flow",
        status=ViewResultStatus.OK,
        as_of=date(2026, 7, 23),
        window=ViewWindow(days=10),
        source="idx",
        scope="full",
        fetch_hint="saham fetch market BBCA",
        data={"rows": []},
    )
    show = ticker_dashboard_to_json_dict(
        TickerDashboard(
            ticker="BBCA",
            mode="brief",
            as_of=date(2026, 7, 23),
            today=date(2026, 7, 24),
            fetch_hint="saham fetch market BBCA",
            panel_keys=panel_keys_for_mode(brief=True),
            freshness=(FreshnessItem("price", "Price", CacheStatus.OK, as_of=date(2026, 7, 23)),),
            related_actions=(
                ViewRelatedAction("flow", "Foreign flow table", "saham view ticker flow BBCA"),
            ),
            panel_errors=(),
            notation=None,
            fundamentals=None,
            forward_estimates=None,
            latest_close=Decimal("1"),
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
    )
    assert set(deep.keys()) == ENVELOPE_KEYS
    assert set(show.keys()) == ENVELOPE_KEYS
    assert show["verb"] == "show"
    assert show["subject"]["kind"] == "ticker"
    assert "related_actions" in show["data"]
    assert "freshness" in show["data"]
