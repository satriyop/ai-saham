"""Offline agent tests for get_ticker_fundamentals_trend."""

from __future__ import annotations

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
from src.application.services.agent_ticker_fundamentals_trend_tool import (
    TickerFundamentalsTrendArguments,
    TickerFundamentalsTrendResultData,
    TickerFundamentalsTrendTool,
)
from src.application.use_case.view_ticker_fundamentals_trend_use_case import (
    EarningsQuarterFacts,
    LatestFundamentalsFacts,
    ViewTickerFundamentalsTrendRequest,
    ViewTickerFundamentalsTrendResult,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


class _FakeUc:
    def __init__(self, result: ViewTickerFundamentalsTrendResult | None) -> None:
        self.result = result
        self.calls: list[ViewTickerFundamentalsTrendRequest] = []

    def execute(self, request: ViewTickerFundamentalsTrendRequest):
        self.calls.append(request)
        return self.result


def _full() -> ViewTickerFundamentalsTrendResult:
    return ViewTickerFundamentalsTrendResult(
        ticker="BBCA",
        requested_quarters=4,
        quarters=(
            EarningsQuarterFacts(
                year=2026,
                quarter=1,
                period_label="Q1 2026",
                eps_actual=120.0,
                eps_estimate=110.0,
                eps_surprise_pct=9.0,
                yoy_growth_pct=8.0,
                beat=True,
            ),
        ),
        eps_trend_direction="rising",
        latest_fundamentals=LatestFundamentalsFacts(
            pe_ratio_ttm=15.0,
            pbv=2.0,
            roe_ttm=18.0,
            net_profit_margin=20.0,
            revenue_yoy_growth=8.0,
            piotroski_f_score=7,
            dividend_yield=2.0,
            market_cap_idr=1_000_000_000_000,
        ),
        forward=None,
        warnings=("FORWARD_ESTIMATES_UNAVAILABLE",),
    )


def test_definition() -> None:
    tool = TickerFundamentalsTrendTool(_FakeUc(None))  # type: ignore[arg-type]
    assert tool.definition.name is AgentToolName.GET_TICKER_FUNDAMENTALS_TREND
    assert tool.definition.side_effect is AgentToolSideEffect.NONE


def test_happy_partial_forward_missing() -> None:
    tool = TickerFundamentalsTrendTool(_FakeUc(_full()))  # type: ignore[arg-type]
    result = tool.execute(
        "f1",
        TickerFundamentalsTrendArguments("BBCA", 4),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert isinstance(result.data, TickerFundamentalsTrendResultData)
    assert result.data.eps_trend_direction == "rising"
    assert result.data.latest_fundamentals is not None
    assert not hasattr(result.data, "quality_score")
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_unavailable() -> None:
    tool = TickerFundamentalsTrendTool(_FakeUc(None))  # type: ignore[arg-type]
    result = tool.execute(
        "u",
        TickerFundamentalsTrendArguments("BBCA", 4),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE


def test_quarters_cap() -> None:
    fake = _FakeUc(_full())
    tool = TickerFundamentalsTrendTool(fake)  # type: ignore[arg-type]
    args = tool.build_arguments(("bbca", "99"))
    assert args.quarters == 8
    tool.execute("c", args, _context())
    assert fake.calls[0].quarters == 8
