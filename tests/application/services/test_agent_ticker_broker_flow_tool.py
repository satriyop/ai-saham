"""Offline agent tests for get_ticker_broker_flow (ADR-061 closed read tool)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolSideEffect,
)
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_ticker_broker_flow_tool import (
    TickerBrokerFlowArguments,
    TickerBrokerFlowResultData,
    TickerBrokerFlowTool,
)
from src.application.use_case.view_ticker_top_brokers_use_case import (
    ViewTickerTopBrokersRequest,
    ViewTickerTopBrokersResult,
)
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent

_SESSION = date(2026, 7, 23)
_OTHER = date(2026, 7, 22)


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _tx(
    code: str,
    *,
    buy: str = "0",
    sell: str = "0",
    avg_buy: str = "1000",
    avg_sell: str = "0",
    name: str | None = None,
) -> BrokerTransaction:
    buy_v = Decimal(buy)
    sell_v = Decimal(sell)
    return BrokerTransaction(
        broker_code=code,
        broker_name=name or f"{code} Desk",
        broker_type=BrokerType.FOREIGN if code in {"YP", "AK"} else BrokerType.LOCAL,
        buy_lot=10 if buy_v else 0,
        sell_lot=10 if sell_v else 0,
        buy_value=buy_v,
        sell_value=sell_v,
        avg_buy_price=Decimal(avg_buy),
        avg_sell_price=Decimal(avg_sell),
    )


def _summary(
    *,
    d: date = _SESSION,
    buyers: tuple[BrokerTransaction, ...] = (),
    sellers: tuple[BrokerTransaction, ...] = (),
) -> BrokerSummary:
    return BrokerSummary(
        ticker="BBCA",
        date=d,
        top_buyers=buyers,
        top_sellers=sellers,
        foreign_buy_value=Decimal("1000"),
        foreign_sell_value=Decimal("500"),
        foreign_buy_lot=10,
        foreign_sell_lot=5,
        total_value=Decimal("10000"),
        total_lot=100,
        source="stockbit",
    )


def _bandar(
    *,
    session: date = _SESSION,
    buyers: int = 12,
    sellers: int = 9,
) -> BandarDetectorSnapshot:
    return BandarDetectorSnapshot(
        ticker="BBCA",
        session_date=session,
        broker_accdist="Acc",
        today_accdist="Small Acc",
        five_day_accdist="Big Acc",
        top1_accdist="Small Acc",
        top1_percent=18.5,
        today_percent=4.2,
        total_buyer=buyers,
        total_seller=sellers,
        top3_accdist="Small Acc",
        top5_accdist="Neutral",
        top10_accdist="Small Acc",
        number_broker_buysell=3,
    )


@dataclass
class _FakeTops:
    result: ViewTickerTopBrokersResult | None
    calls: list[ViewTickerTopBrokersRequest]

    def __init__(self, result: ViewTickerTopBrokersResult | None) -> None:
        self.result = result
        self.calls = []

    def execute(self, request: ViewTickerTopBrokersRequest) -> ViewTickerTopBrokersResult | None:
        self.calls.append(request)
        return self.result


@dataclass
class _FakeBandar:
    by_date: dict[date, BandarDetectorSnapshot | None]
    calls: list[tuple[str, date]]

    def __init__(self, by_date: dict[date, BandarDetectorSnapshot | None] | None = None) -> None:
        self.by_date = dict(by_date or {})
        self.calls = []

    def get_bandar(self, ticker: str, session_date: date) -> BandarDetectorSnapshot | None:
        self.calls.append((ticker, session_date))
        return self.by_date.get(session_date)


def _happy_tops(*, limit_applied: int = 10) -> ViewTickerTopBrokersResult:
    buyers = (
        _tx("YP", buy="5_000_000", avg_buy="10250"),
        _tx("AK", buy="3_000_000", avg_buy="10100"),
        _tx("CC", buy="1_000_000", avg_buy="10050"),
    )
    sellers = (
        _tx("XL", sell="4_000_000", avg_sell="10300"),
        _tx("ZP", sell="2_000_000", avg_sell="10200"),
    )
    return ViewTickerTopBrokersResult(
        ticker="BBCA",
        date=_SESSION,
        summary=_summary(buyers=buyers, sellers=sellers),
        top_buyers=buyers[:limit_applied],
        top_sellers=sellers[:limit_applied],
        tops_source="summary",
        tops_scope=None,
        tops_scope_note=None,
    )


def test_definition_is_closed_read_none_approval() -> None:
    tool = TickerBrokerFlowTool(_FakeTops(None), _FakeBandar())
    assert tool.definition.name is AgentToolName.GET_TICKER_BROKER_FLOW
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert tool.definition.approval.value == "NONE"
    assert tool.definition.max_result_bytes <= 32 * 1024


def test_happy_path_named_desks_counts_labels_and_avg_prices() -> None:
    tops = _FakeTops(_happy_tops())
    bandar = _FakeBandar({_SESSION: _bandar()})
    tool = TickerBrokerFlowTool(tops, bandar)

    result = tool.execute(
        "flow-1",
        TickerBrokerFlowArguments("BBCA", None, 10),
        _context(),
    )

    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, TickerBrokerFlowResultData)
    assert result.data.ticker == "BBCA"
    assert result.data.as_of == _SESSION
    assert result.data.tops_source == "summary"
    assert len(result.data.top_accumulating) == 3
    assert len(result.data.top_distributing) == 2
    lead = result.data.top_accumulating[0]
    assert lead.broker_code == "YP"
    assert lead.side == "buy"
    assert lead.avg_buy_price == "10250"
    assert lead.net_value_idr == "5000000"
    assert result.data.bandar is not None
    assert result.data.bandar.total_buyers == 12
    assert result.data.bandar.total_sellers == 9
    assert result.data.bandar.five_day_accdist == "Big Acc"
    assert result.data.bandar.top3_accdist == "Small Acc"
    assert result.data.bandar.number_broker_buysell == 3
    assert bandar.calls == [("BBCA", _SESSION)]
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_limit_above_ten_is_capped() -> None:
    args = TickerBrokerFlowTool(_FakeTops(None), _FakeBandar()).build_arguments(("BBCA", "", "25"))
    assert args.limit == 10

    codes = ["YP", "AK", "CC", "XL", "ZP", "RX", "KK", "EP", "YU", "PD", "MG", "NI"]
    many_buyers = tuple(_tx(codes[i], buy=str(1_000_000 * (12 - i))) for i in range(12))
    sellers = (_tx("ZZ", sell="1000"),)
    tops_result = ViewTickerTopBrokersResult(
        ticker="BBCA",
        date=_SESSION,
        summary=_summary(buyers=many_buyers[:10], sellers=sellers),
        top_buyers=many_buyers[:10],
        top_sellers=sellers,
        tops_source="summary",
        tops_scope=None,
        tops_scope_note=None,
    )
    tops = _FakeTops(tops_result)
    tool = TickerBrokerFlowTool(tops, _FakeBandar({_SESSION: _bandar()}))
    result = tool.execute(
        "cap",
        TickerBrokerFlowArguments("BBCA", None, 10),
        _context(),
    )
    assert isinstance(result.data, TickerBrokerFlowResultData)
    assert len(result.data.top_accumulating) == 10
    assert tops.calls[0].limit == 10


def test_explicit_target_date_forwarded_and_bandar_uses_resolved_tops_date() -> None:
    """Bandar must use tops.date even when request target_date differs in value path."""
    tops_result = _happy_tops()
    # tops resolve to _SESSION regardless of request; assert bandar gets tops.date
    tops = _FakeTops(tops_result)
    bandar = _FakeBandar({_SESSION: _bandar(), _OTHER: _bandar(session=_OTHER, buyers=1)})
    tool = TickerBrokerFlowTool(tops, bandar)

    result = tool.execute(
        "dated",
        TickerBrokerFlowArguments("BBCA", _OTHER, 5),
        _context(),
    )

    assert tops.calls[0].target_date == _OTHER
    assert tops.calls[0].limit == 5
    assert bandar.calls == [("BBCA", _SESSION)]  # tops resolved date, not raw target
    assert result.data is not None
    assert result.data.as_of == _SESSION
    assert result.data.bandar is not None
    assert result.data.bandar.total_buyers == 12


def test_missing_all_backing_data_is_unavailable_no_fabricated_desks() -> None:
    tool = TickerBrokerFlowTool(_FakeTops(None), _FakeBandar())
    result = tool.execute(
        "miss",
        TickerBrokerFlowArguments("BBCA", None, 10),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None
    assert result.error_code == "TICKER_BROKER_FLOW_UNAVAILABLE"
    assert "fabricat" not in (result.error_message or "").lower()


def test_empty_tops_with_bandar_is_success_info_no_net_tops() -> None:
    empty = ViewTickerTopBrokersResult(
        ticker="BBCA",
        date=_SESSION,
        summary=_summary(),
        top_buyers=(),
        top_sellers=(),
        tops_source="summary",
        tops_scope=None,
        tops_scope_note=None,
    )
    tool = TickerBrokerFlowTool(_FakeTops(empty), _FakeBandar({_SESSION: _bandar()}))
    result = tool.execute(
        "empty",
        TickerBrokerFlowArguments("BBCA", None, 10),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert "NO_NET_TOPS" in result.warnings
    assert isinstance(result.data, TickerBrokerFlowResultData)
    assert result.data.top_accumulating == ()
    assert result.data.top_distributing == ()
    assert result.data.bandar is not None


def test_one_sided_tops_info_codes() -> None:
    buyers_only = ViewTickerTopBrokersResult(
        ticker="BBCA",
        date=_SESSION,
        summary=_summary(buyers=(_tx("YP", buy="1000"),)),
        top_buyers=(_tx("YP", buy="1000"),),
        top_sellers=(),
        tops_source="summary",
        tops_scope=None,
        tops_scope_note=None,
    )
    tool = TickerBrokerFlowTool(_FakeTops(buyers_only), _FakeBandar({_SESSION: _bandar()}))
    result = tool.execute(
        "one",
        TickerBrokerFlowArguments("BBCA", None, 10),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert "NO_DISTRIBUTION_SIDE" in result.warnings


def test_named_tops_present_bandar_missing_is_partial() -> None:
    tool = TickerBrokerFlowTool(_FakeTops(_happy_tops()), _FakeBandar())
    result = tool.execute(
        "no-bandar",
        TickerBrokerFlowArguments("BBCA", None, 10),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "BANDAR_SNAPSHOT_UNAVAILABLE" in result.warnings
    assert isinstance(result.data, TickerBrokerFlowResultData)
    assert result.data.bandar is None
    assert len(result.data.top_accumulating) == 3


def test_bandar_present_tops_missing_is_partial() -> None:
    bandar = _FakeBandar({_OTHER: _bandar(session=_OTHER)})
    tool = TickerBrokerFlowTool(_FakeTops(None), bandar)
    result = tool.execute(
        "no-tops",
        TickerBrokerFlowArguments("BBCA", _OTHER, 10),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "NAMED_TOPS_UNAVAILABLE" in result.warnings
    assert isinstance(result.data, TickerBrokerFlowResultData)
    assert result.data.top_accumulating == ()
    assert result.data.bandar is not None
    assert bandar.calls == [("BBCA", _OTHER)]


def test_tracked_fallback_empty_is_partial() -> None:
    empty_tracked = ViewTickerTopBrokersResult(
        ticker="BBCA",
        date=_SESSION,
        summary=_summary(),
        top_buyers=(),
        top_sellers=(),
        tops_source="broker_daily_flow",
        tops_scope="tracked_brokers",
        tops_scope_note="Tracked only",
    )
    tool = TickerBrokerFlowTool(
        _FakeTops(empty_tracked),
        _FakeBandar({_SESSION: _bandar()}),
    )
    result = tool.execute(
        "fb",
        TickerBrokerFlowArguments("BBCA", None, 10),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "TOPS_FALLBACK_EMPTY" in result.warnings
    assert result.data is not None
    assert result.data.tops_scope == "tracked_brokers"


def test_build_arguments_parses_optional_fields() -> None:
    tool = TickerBrokerFlowTool(_FakeTops(None), _FakeBandar())
    args = tool.build_arguments(("bbca", "2026-07-22", ""))
    assert args.ticker == "BBCA"
    assert args.target_date == _OTHER
    assert args.limit == 10
