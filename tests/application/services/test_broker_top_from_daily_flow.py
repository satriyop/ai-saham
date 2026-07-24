"""Tests for ranking top brokers from tracked daily-flow rows."""

from datetime import date
from decimal import Decimal

import pytest

from src.application.services.broker_top_from_daily_flow import (
    TRACKED_TOPS_NOTE,
    daily_flow_to_transaction,
    rank_top_brokers_from_daily_flows,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerType


def _flow(
    code: str,
    net_value: str,
    *,
    buy_lot: int = 0,
    sell_lot: int = 0,
    buy_value: str = "0",
    sell_value: str = "0",
) -> BrokerDailyFlow:
    net = Decimal(net_value)
    return BrokerDailyFlow(
        ticker="BBCA",
        broker_code=code,
        broker_name=code,
        date=date(2026, 7, 23),
        buy_lot=buy_lot,
        sell_lot=sell_lot,
        net_lot=buy_lot - sell_lot,
        buy_value=Decimal(buy_value),
        sell_value=Decimal(sell_value),
        net_value=net,
        avg_buy_price=Decimal("0"),
        avg_sell_price=Decimal("0"),
        avg_price=Decimal("0"),
        buy_pct=0.0,
        sell_pct=0.0,
        source="stockbit",
    )


def test_rank_separates_buyers_and_sellers_by_net_value():
    flows = [
        _flow("YP", "72095542500", buy_value="72095542500", buy_lot=100),
        _flow("XL", "65460180000", buy_value="65460180000", buy_lot=90),
        _flow("RX", "-163217637500", sell_value="163217637500", sell_lot=200),
        _flow("AK", "-61158415000", sell_value="61158415000", sell_lot=80),
        _flow("KZ", "0"),  # flat — omitted
    ]

    buyers, sellers = rank_top_brokers_from_daily_flows(flows, limit=10)

    assert [b.broker_code for b in buyers] == ["YP", "XL"]
    assert [s.broker_code for s in sellers] == ["RX", "AK"]  # most negative first
    assert buyers[0].net_value == Decimal("72095542500")
    assert sellers[0].net_value == Decimal("-163217637500")


def test_rank_respects_limit():
    flows = [
        _flow("A", "5", buy_value="5"),
        _flow("B", "4", buy_value="4"),
        _flow("C", "3", buy_value="3"),
        _flow("D", "-1", sell_value="1"),
        _flow("E", "-2", sell_value="2"),
        _flow("F", "-3", sell_value="3"),
    ]
    buyers, sellers = rank_top_brokers_from_daily_flows(flows, limit=2)
    assert [b.broker_code for b in buyers] == ["A", "B"]
    assert [s.broker_code for s in sellers] == ["F", "E"]


def test_rank_empty_input():
    buyers, sellers = rank_top_brokers_from_daily_flows([])
    assert buyers == ()
    assert sellers == ()


def test_rank_rejects_invalid_limit():
    with pytest.raises(ValueError, match="limit"):
        rank_top_brokers_from_daily_flows([], limit=0)


def test_daily_flow_maps_type_unknown_without_classification():
    tx = daily_flow_to_transaction(_flow("YP", "1", buy_value="1", buy_lot=1))
    assert tx.broker_type == BrokerType.UNKNOWN
    assert tx.broker_code == "YP"
    assert TRACKED_TOPS_NOTE.startswith("Tracked brokers")


def test_daily_flow_classifies_foreign_and_local_from_config_set():
    foreign = frozenset({"AK", "BK", "RX"})
    foreign_tx = daily_flow_to_transaction(
        _flow("AK", "1", buy_value="1", buy_lot=1),
        foreign_broker_codes=foreign,
    )
    local_tx = daily_flow_to_transaction(
        _flow("YP", "1", buy_value="1", buy_lot=1),
        foreign_broker_codes=foreign,
    )
    assert foreign_tx.broker_type == BrokerType.FOREIGN
    assert local_tx.broker_type == BrokerType.LOCAL


def test_rank_propagates_classified_types():
    foreign = frozenset({"RX"})
    buyers, sellers = rank_top_brokers_from_daily_flows(
        [
            _flow("YP", "10", buy_value="10"),
            _flow("RX", "-20", sell_value="20"),
        ],
        foreign_broker_codes=foreign,
    )
    assert buyers[0].broker_type == BrokerType.LOCAL
    assert sellers[0].broker_type == BrokerType.FOREIGN
