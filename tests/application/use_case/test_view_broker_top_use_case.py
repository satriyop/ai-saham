"""Tests for ViewBrokerTopUseCase summary tops + tracked daily-flow fallback."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.services.broker_top_from_daily_flow import (
    TRACKED_TOPS_NOTE,
    TRACKED_TOPS_SCOPE,
    TRACKED_TOPS_SOURCE,
)
from src.application.use_case.view_broker_top_use_case import (
    ViewBrokerTopRequest,
    ViewBrokerTopUseCase,
)
from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
)


def _summary(
    *,
    d: date = date(2026, 7, 23),
    top_buyers: tuple = (),
    top_sellers: tuple = (),
    source: str = "idx",
) -> BrokerSummary:
    return BrokerSummary(
        ticker="BBCA",
        date=d,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=Decimal("100"),
        foreign_sell_value=Decimal("50"),
        foreign_buy_lot=10,
        foreign_sell_lot=5,
        total_value=Decimal("1000"),
        total_lot=100,
        source=source,
    )


def _tx(code: str, net: str) -> BrokerTransaction:
    value = Decimal(net)
    buy = value if value > 0 else Decimal("0")
    sell = -value if value < 0 else Decimal("0")
    return BrokerTransaction(
        broker_code=code,
        broker_name=code,
        broker_type=BrokerType.FOREIGN,
        buy_lot=1 if buy else 0,
        sell_lot=1 if sell else 0,
        buy_value=buy,
        sell_value=sell,
        avg_buy_price=Decimal("0"),
        avg_sell_price=Decimal("0"),
    )


def _flow(code: str, net: str) -> BrokerDailyFlow:
    value = Decimal(net)
    buy = value if value > 0 else Decimal("0")
    sell = -value if value < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker="BBCA",
        broker_code=code,
        broker_name=code,
        date=date(2026, 7, 23),
        buy_lot=1 if buy else 0,
        sell_lot=1 if sell else 0,
        net_lot=1 if buy else -1,
        buy_value=buy,
        sell_value=sell,
        net_value=value,
        avg_buy_price=Decimal("0"),
        avg_sell_price=Decimal("0"),
        avg_price=Decimal("0"),
        buy_pct=0.0,
        sell_pct=0.0,
    )


def test_prefers_summary_tops_when_present():
    repo = MagicMock()
    summary = _summary(
        top_buyers=(_tx("MS", "100"),),
        top_sellers=(_tx("YP", "-50"),),
        source="stockbit",
    )
    repo.get_broker_summaries.return_value = [summary]

    result = ViewBrokerTopUseCase(repo).execute(ViewBrokerTopRequest(ticker="bbca"))

    assert result is not None
    assert result.tops_source == "summary"
    assert result.tops_scope is None
    assert result.tops_scope_note is None
    assert [b.broker_code for b in result.top_buyers] == ["MS"]
    assert [s.broker_code for s in result.top_sellers] == ["YP"]
    repo.get_broker_daily_flows.assert_not_called()


def test_falls_back_to_tracked_daily_flow_when_summary_tops_empty():
    repo = MagicMock()
    summary = _summary(top_buyers=(), top_sellers=())
    repo.get_broker_summaries.return_value = [summary]
    repo.get_broker_daily_flows.return_value = [
        _flow("YP", "70"),
        _flow("XL", "60"),
        _flow("RX", "-160"),
        _flow("AK", "-60"),
    ]
    foreign = frozenset({"RX", "AK"})

    result = ViewBrokerTopUseCase(
        repo,
        foreign_broker_codes=foreign,
    ).execute(ViewBrokerTopRequest(ticker="BBCA"))

    assert result is not None
    assert result.tops_source == TRACKED_TOPS_SOURCE
    assert result.tops_scope == TRACKED_TOPS_SCOPE
    assert result.tops_scope_note == TRACKED_TOPS_NOTE
    assert [b.broker_code for b in result.top_buyers] == ["YP", "XL"]
    assert [s.broker_code for s in result.top_sellers] == ["RX", "AK"]
    assert all(b.broker_type == BrokerType.LOCAL for b in result.top_buyers)
    assert all(s.broker_type == BrokerType.FOREIGN for s in result.top_sellers)
    repo.get_broker_daily_flows.assert_called_once_with(
        "BBCA",
        start_date=date(2026, 7, 23),
        end_date=date(2026, 7, 23),
    )


def test_empty_tops_and_no_daily_flow_returns_empty_lists_without_tracked_label():
    repo = MagicMock()
    repo.get_broker_summaries.return_value = [_summary()]
    repo.get_broker_daily_flows.return_value = []

    result = ViewBrokerTopUseCase(repo).execute(ViewBrokerTopRequest(ticker="BBCA"))

    assert result is not None
    assert result.top_buyers == ()
    assert result.top_sellers == ()
    assert result.tops_source == "summary"
    assert result.tops_scope_note is None


def test_target_date_uses_get_broker_summary():
    repo = MagicMock()
    d = date(2026, 6, 12)
    summary = _summary(d=d, top_buyers=(_tx("ZP", "10"),))
    repo.get_broker_summary.return_value = summary

    result = ViewBrokerTopUseCase(repo).execute(
        ViewBrokerTopRequest(ticker="BBCA", target_date=d)
    )

    assert result is not None
    assert result.date == d
    repo.get_broker_summary.assert_called_once_with("BBCA", d)
    repo.get_broker_summaries.assert_not_called()


def test_returns_none_when_no_summary():
    repo = MagicMock()
    repo.get_broker_summaries.return_value = []

    result = ViewBrokerTopUseCase(repo).execute(ViewBrokerTopRequest(ticker="BBCA"))

    assert result is None
