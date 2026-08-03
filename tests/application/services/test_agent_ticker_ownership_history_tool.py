"""Offline agent tests for get_ticker_ownership_history (ADR-061 closed read tool)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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
from src.application.services.agent_ticker_ownership_history_tool import (
    TickerOwnershipHistoryArguments,
    TickerOwnershipHistoryResultData,
    TickerOwnershipHistoryTool,
)
from src.application.use_case.view_ticker_ownership_history_use_case import (
    ViewTickerOwnershipHistoryRequest,
    ViewTickerOwnershipHistoryResult,
)
from src.domain.value_objects.shareholding_composition import ShareholdingComposition
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _comp(
    report_date: date,
    *,
    institution_pct: float = 40.0,
    individual_pct: float = 25.0,
    top_holder_pct: float = 30.0,
) -> ShareholdingComposition:
    return ShareholdingComposition(
        ticker="BBCA",
        report_date=report_date,
        institution_pct=institution_pct,
        individual_pct=individual_pct,
        top_holder_name="DWIMURIA",
        top_holder_pct=top_holder_pct,
        total_shares=100_000_000,
        total_shares_formatted="100M",
    )


@dataclass
class _FakeHistory:
    result: ViewTickerOwnershipHistoryResult | None
    calls: list[ViewTickerOwnershipHistoryRequest]

    def __init__(self, result: ViewTickerOwnershipHistoryResult | None) -> None:
        self.result = result
        self.calls = []

    def execute(
        self, request: ViewTickerOwnershipHistoryRequest
    ) -> ViewTickerOwnershipHistoryResult | None:
        self.calls.append(request)
        return self.result


def test_definition_is_closed_read_none_approval() -> None:
    tool = TickerOwnershipHistoryTool(_FakeHistory(None))
    assert tool.definition.name is AgentToolName.GET_TICKER_OWNERSHIP_HISTORY
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert tool.definition.approval.value == "NONE"
    assert (
        "score" not in tool.definition.description.lower()
        or "not a" in tool.definition.description.lower()
    )


def test_multi_period_happy_path() -> None:
    periods = (
        _comp(date(2026, 3, 31), institution_pct=40.0, top_holder_pct=30.0),
        _comp(date(2026, 6, 30), institution_pct=42.0, top_holder_pct=31.0),
    )
    result = ViewTickerOwnershipHistoryResult(
        ticker="BBCA",
        as_of=date(2026, 6, 30),
        periods=periods,
        institution_pct_change=2.0,
        float_change=3.0,
        top_holder_pct_change=1.0,
    )
    fake = _FakeHistory(result)
    tool = TickerOwnershipHistoryTool(fake)
    out = tool.execute("h-1", TickerOwnershipHistoryArguments("BBCA", 8), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(out.data, TickerOwnershipHistoryResultData)
    assert out.data.ticker == "BBCA"
    assert out.data.period_count == 2
    assert out.data.institution_pct_change == 2.0
    assert out.data.float_change == 3.0
    assert out.data.top_holder_pct_change == 1.0
    assert out.data.periods[0].free_float_pct == 65.0  # 40 + 25
    assert "SINGLE_PERIOD_ONLY" not in out.warnings
    assert fake.calls[0].limit == 8
    assert out.serialized_size() <= tool.definition.max_result_bytes
    assert not hasattr(out.data, "score")
    assert not hasattr(out.data, "strength")
    assert not hasattr(out.data, "quality")


def test_single_period_is_success_with_info_note() -> None:
    result = ViewTickerOwnershipHistoryResult(
        ticker="BBCA",
        as_of=date(2026, 3, 31),
        periods=(_comp(date(2026, 3, 31)),),
        institution_pct_change=None,
        float_change=None,
        top_holder_pct_change=None,
    )
    tool = TickerOwnershipHistoryTool(_FakeHistory(result))
    out = tool.execute("single", TickerOwnershipHistoryArguments("BBCA", 8), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert "SINGLE_PERIOD_ONLY" in out.warnings
    assert isinstance(out.data, TickerOwnershipHistoryResultData)
    assert out.data.period_count == 1
    assert out.data.institution_pct_change is None


def test_missing_cache_is_unavailable() -> None:
    tool = TickerOwnershipHistoryTool(_FakeHistory(None))
    out = tool.execute("miss", TickerOwnershipHistoryArguments("BBCA", 8), _context())
    assert out.status is AgentToolExecutionStatus.UNAVAILABLE
    assert out.data is None
    assert out.error_code == "TICKER_OWNERSHIP_HISTORY_UNAVAILABLE"


def test_read_failure_is_failed() -> None:
    class _Raising:
        def execute(self, request):
            raise RuntimeError("boom")

    tool = TickerOwnershipHistoryTool(_Raising())
    out = tool.execute("fail", TickerOwnershipHistoryArguments("BBCA", 8), _context())
    assert out.status is AgentToolExecutionStatus.FAILED
    assert out.error_code == "TICKER_OWNERSHIP_HISTORY_READ_FAILED"
    assert out.retryable is False


def test_limit_above_max_capped_and_default_applied() -> None:
    tool = TickerOwnershipHistoryTool(_FakeHistory(None))
    args = tool.build_arguments(("bbca", "999"))
    assert args.ticker == "BBCA"
    assert args.limit == 8
    assert tool.build_arguments(("BBCA", "")).limit == 8


def test_argument_validation_rejects_bad_ticker_and_limit() -> None:
    tool = TickerOwnershipHistoryTool(_FakeHistory(None))
    with pytest.raises(ValueError):
        tool.build_arguments(("TOO_LONG", "8"))
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", "0"))
