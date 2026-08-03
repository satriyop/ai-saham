"""Offline agent tests for get_ticker_desk_flow_history."""

from __future__ import annotations

from datetime import date, timedelta
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
from src.application.services.agent_ticker_desk_flow_history_tool import (
    TickerDeskFlowHistoryArguments,
    TickerDeskFlowHistoryResultData,
    TickerDeskFlowHistoryTool,
)
from src.application.services.ticker_desk_flow_history import (
    TickerDeskFlowHistoryService,
)
from src.domain.entities.broker_flow import BrokerDailyFlow
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _flow(code: str, d: date, net: str) -> BrokerDailyFlow:
    net_v = Decimal(net)
    buy = net_v if net_v > 0 else Decimal("0")
    sell = -net_v if net_v < 0 else Decimal("0")
    return BrokerDailyFlow(
        ticker="BBCA",
        broker_code=code,
        broker_name=f"{code} Desk",
        date=d,
        buy_lot=1,
        sell_lot=1 if sell else 0,
        net_lot=1 if buy else -1,
        buy_value=buy,
        sell_value=sell,
        net_value=net_v,
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
        avg_price=Decimal("1000"),
        buy_pct=0.0,
        sell_pct=0.0,
    )


class _MemSource:
    def __init__(self, flows: list[BrokerDailyFlow]) -> None:
        self.flows = flows

    def get_broker_daily_flow_date_range(self, ticker: str, source: str | None = None):
        del source
        rows = [f for f in self.flows if f.ticker == ticker.upper()]
        if not rows:
            return None
        dates = sorted(f.date for f in rows)
        return dates[0], dates[-1]

    def get_broker_daily_flows(
        self,
        ticker: str,
        start_date=None,
        end_date=None,
        broker_codes=None,
        source=None,
    ):
        del broker_codes, source
        out = []
        for f in self.flows:
            if f.ticker != ticker.upper():
                continue
            if start_date and f.date < start_date:
                continue
            if end_date and f.date > end_date:
                continue
            out.append(f)
        return out


def test_definition_closed_read_no_score() -> None:
    tool = TickerDeskFlowHistoryTool(
        TickerDeskFlowHistoryService(_MemSource([]), foreign_broker_codes=frozenset())
    )
    assert tool.definition.name is AgentToolName.GET_TICKER_DESK_FLOW_HISTORY
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert "score" in tool.definition.description.lower()
    assert "not" in tool.definition.description.lower()


def test_happy_path_and_caps() -> None:
    end = date(2026, 7, 31)
    flows = []
    for i in range(20):
        d = end - timedelta(days=19 - i)
        flows.append(_flow("YP", d, "100"))
        flows.append(_flow("EP", d, "-50"))
    svc = TickerDeskFlowHistoryService(
        _MemSource(flows),
        foreign_broker_codes=frozenset({"YP"}),
    )
    tool = TickerDeskFlowHistoryTool(svc)
    args = tool.build_arguments(("bbca", "90", "25", ""))
    assert args.sessions == 60
    assert args.limit == 10
    result = tool.execute("h1", TickerDeskFlowHistoryArguments("BBCA", 20, 5, None), _context())
    assert result.status in {
        AgentToolExecutionStatus.SUCCESS,
        AgentToolExecutionStatus.PARTIAL,
    }
    assert isinstance(result.data, TickerDeskFlowHistoryResultData)
    assert result.data.top_accumulating[0].broker_code == "YP"
    assert result.data.top_distributing[0].broker_code == "EP"
    assert not hasattr(result.data, "score")
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_missing_is_unavailable() -> None:
    tool = TickerDeskFlowHistoryTool(
        TickerDeskFlowHistoryService(_MemSource([]), foreign_broker_codes=frozenset())
    )
    result = tool.execute(
        "miss",
        TickerDeskFlowHistoryArguments("BBCA", 60, 10, None),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None
