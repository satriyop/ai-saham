"""Unit tests for stock deep-dive view use cases."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.use_case.view_ticker_distribution_use_case import (
    ViewTickerDistributionRequest,
    ViewTickerDistributionUseCase,
)
from src.application.use_case.view_ticker_flow_use_case import (
    ViewTickerFlowRequest,
    ViewTickerFlowUseCase,
)
from src.application.use_case.view_ticker_foreign_history_use_case import (
    ViewTickerForeignHistoryRequest,
    ViewTickerForeignHistoryUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary, ForeignFlowPoint
from src.domain.value_objects.broker_distribution import BrokerDistributionSnapshot


def test_foreign_history_auto_prefers_stockbit():
    repo = MagicMock()
    repo.get_foreign_flow_points.side_effect = lambda ticker, source=None: (
        [
            ForeignFlowPoint(
                ticker="BBCA",
                date=date(2026, 7, 23),
                net_val=Decimal("-1"),
                net_lot=-1,
                avg_price=Decimal("6000"),
                source="stockbit",
            )
        ]
        if source == "stockbit"
        else [
            ForeignFlowPoint(
                ticker="BBCA",
                date=date(2026, 7, 23),
                net_val=Decimal("2"),
                net_lot=2,
                avg_price=Decimal("0"),
                source="idx",
            )
        ]
    )
    result = ViewTickerForeignHistoryUseCase(repo).execute(
        ViewTickerForeignHistoryRequest(ticker="bbca", days=5, source="auto")
    )
    assert result is not None
    assert result.resolved_source == "stockbit"
    assert result.points[0].net_val == Decimal("-1")


def test_foreign_history_returns_none_when_empty():
    repo = MagicMock()
    repo.get_foreign_flow_points.return_value = []
    result = ViewTickerForeignHistoryUseCase(repo).execute(
        ViewTickerForeignHistoryRequest(ticker="BBCA", days=10, source="stockbit")
    )
    assert result is None


def test_flow_use_case_windows_and_totals():
    repo = MagicMock()
    repo.get_broker_summaries.return_value = [
        BrokerSummary(
            ticker="BBCA",
            date=date(2026, 7, 21),
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("100"),
            foreign_sell_value=Decimal("40"),
            foreign_buy_lot=1,
            foreign_sell_lot=1,
            total_value=Decimal("1000"),
            total_lot=10,
            source="idx",
        ),
        BrokerSummary(
            ticker="BBCA",
            date=date(2026, 7, 22),
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("10"),
            foreign_sell_value=Decimal("50"),
            foreign_buy_lot=1,
            foreign_sell_lot=1,
            total_value=Decimal("1000"),
            total_lot=10,
            source="idx",
        ),
        BrokerSummary(
            ticker="BBCA",
            date=date(2026, 7, 23),
            top_buyers=(),
            top_sellers=(),
            foreign_buy_value=Decimal("20"),
            foreign_sell_value=Decimal("80"),
            foreign_buy_lot=1,
            foreign_sell_lot=1,
            total_value=Decimal("1000"),
            total_lot=10,
            source="idx",
        ),
    ]
    result = ViewTickerFlowUseCase(repo).execute(
        ViewTickerFlowRequest(ticker="BBCA", days=2, as_of=date(2026, 7, 24))
    )
    assert result is not None
    assert len(result.summaries) == 2
    assert result.as_of == date(2026, 7, 23)
    assert result.buy_days == 0
    assert result.sell_days == 2
    assert result.total_net_value == Decimal("-100")
    assert result.source == "idx"


def test_distribution_use_case_wraps_provider():
    provider = MagicMock()
    snap = BrokerDistributionSnapshot(
        ticker="BBCA",
        date=date(2026, 7, 23),
        top_buyers=(),
        top_sellers=(),
    )
    provider.get_distribution.return_value = snap
    result = ViewTickerDistributionUseCase(provider).execute(
        ViewTickerDistributionRequest(ticker="bbca")
    )
    assert result is not None
    assert result.as_of == date(2026, 7, 23)
    assert result.source == "broker_distribution_cache"
    provider.get_distribution.assert_called_once_with("BBCA", None)
