"""Offline agent tests for get_ticker_foreign_flow (ADR-061 closed read tool)."""

from __future__ import annotations

from dataclasses import dataclass
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
from src.application.services.agent_ticker_foreign_flow_tool import (
    TickerForeignFlowArguments,
    TickerForeignFlowResultData,
    TickerForeignFlowTool,
    trend_direction_from_series,
)
from src.application.use_case.view_ticker_foreign_history_use_case import (
    ViewTickerForeignHistoryRequest,
    ViewTickerForeignHistoryResult,
)
from src.domain.entities.broker_flow import ForeignFlowPoint
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent

_AS_OF = date(2026, 7, 31)


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _pt(d: date, net: str) -> ForeignFlowPoint:
    return ForeignFlowPoint(
        ticker="BBCA",
        date=d,
        net_val=Decimal(net),
        net_lot=10,
        avg_price=Decimal("1000"),
        source="stockbit",
    )


def _series(*, n: int = 10, rising: bool = True) -> tuple[ForeignFlowPoint, ...]:
    points: list[ForeignFlowPoint] = []
    for i in range(n):
        d = _AS_OF - timedelta(days=n - 1 - i)
        # rising: later sessions more positive
        net = str((i + 1) * 1000) if rising else str((n - i) * 1000)
        if not rising and i > n // 2:
            net = str(-abs(int(net)))
        points.append(_pt(d, net))
    return tuple(points)


@dataclass
class _FakeHistory:
    result: ViewTickerForeignHistoryResult | None
    calls: list[ViewTickerForeignHistoryRequest]

    def __init__(self, result: ViewTickerForeignHistoryResult | None) -> None:
        self.result = result
        self.calls = []

    def execute(
        self, request: ViewTickerForeignHistoryRequest
    ) -> ViewTickerForeignHistoryResult | None:
        self.calls.append(request)
        return self.result


def _ok_result(
    points: tuple[ForeignFlowPoint, ...],
    *,
    days: int = 30,
) -> ViewTickerForeignHistoryResult:
    return ViewTickerForeignHistoryResult(
        ticker="BBCA",
        days=days,
        requested_source="auto",
        resolved_source="stockbit",
        points=points,
        as_of=points[-1].date if points else None,
    )


def test_definition_is_closed_read_none_approval() -> None:
    tool = TickerForeignFlowTool(_FakeHistory(None))
    assert tool.definition.name is AgentToolName.GET_TICKER_FOREIGN_FLOW
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert tool.definition.approval.value == "NONE"
    # No score vocabulary in description
    assert (
        "score" not in tool.definition.description.lower()
        or "not a" in tool.definition.description.lower()
    )


def test_happy_path_summary_and_tail() -> None:
    points = _series(n=30, rising=True)
    fake = _FakeHistory(_ok_result(points, days=30))
    tool = TickerForeignFlowTool(fake)
    result = tool.execute(
        "ff-1",
        TickerForeignFlowArguments("BBCA", 30),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, TickerForeignFlowResultData)
    assert result.data.ticker == "BBCA"
    assert result.data.resolved_source == "stockbit"
    assert result.data.active_sessions == 30
    assert result.data.requested_days == 30
    assert result.data.trend_direction == "rising"
    assert result.data.latest_net_idr == str(points[-1].net_val)
    assert len(result.data.points) == 30
    assert fake.calls[0].source == "auto"
    assert result.serialized_size() <= tool.definition.max_result_bytes
    # No score-like fields on result
    assert not hasattr(result.data, "score")
    assert not hasattr(result.data, "strength")
    assert not hasattr(result.data, "quality")


def test_days_above_sixty_capped() -> None:
    args = TickerForeignFlowTool(_FakeHistory(None)).build_arguments(("BBCA", "90"))
    assert args.days == 60
    assert TickerForeignFlowTool(_FakeHistory(None)).build_arguments(("bbca", "")).days == 30


def test_window_shorter_than_requested_is_partial() -> None:
    points = _series(n=5, rising=True)
    tool = TickerForeignFlowTool(_FakeHistory(_ok_result(points, days=5)))
    result = tool.execute(
        "short",
        TickerForeignFlowArguments("BBCA", 30),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "FOREIGN_WINDOW_SHORT" in result.warnings
    assert isinstance(result.data, TickerForeignFlowResultData)
    assert result.data.active_sessions == 5
    assert result.data.requested_days == 30


def test_missing_cache_is_unavailable() -> None:
    tool = TickerForeignFlowTool(_FakeHistory(None))
    result = tool.execute(
        "miss",
        TickerForeignFlowArguments("BBCA", 30),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None
    assert result.error_code == "TICKER_FOREIGN_FLOW_UNAVAILABLE"


def test_point_tail_capped_at_thirty() -> None:
    points = _series(n=45, rising=True)
    tool = TickerForeignFlowTool(_FakeHistory(_ok_result(points, days=45)))
    result = tool.execute(
        "tail",
        TickerForeignFlowArguments("BBCA", 60),
        _context(),
    )
    assert isinstance(result.data, TickerForeignFlowResultData)
    assert len(result.data.points) == 30
    assert result.data.points[-1].date == points[-1].date


def test_trend_direction_half_window() -> None:
    # first half small, second half large → rising
    rising = (
        _pt(date(2026, 7, 1), "100"),
        _pt(date(2026, 7, 2), "100"),
        _pt(date(2026, 7, 3), "5000"),
        _pt(date(2026, 7, 4), "5000"),
    )
    assert trend_direction_from_series(rising) == "rising"
    falling = (
        _pt(date(2026, 7, 1), "5000"),
        _pt(date(2026, 7, 2), "5000"),
        _pt(date(2026, 7, 3), "100"),
        _pt(date(2026, 7, 4), "100"),
    )
    assert trend_direction_from_series(falling) == "falling"
    flat = (
        _pt(date(2026, 7, 1), "1000"),
        _pt(date(2026, 7, 2), "1000"),
    )
    assert trend_direction_from_series(flat) == "flat"
