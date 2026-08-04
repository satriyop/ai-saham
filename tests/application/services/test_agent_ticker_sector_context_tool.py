"""Offline agent tests for get_ticker_sector_context."""

from __future__ import annotations

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
from src.application.services.agent_ticker_sector_context_tool import (
    TickerSectorContextArguments,
    TickerSectorContextResultData,
    TickerSectorContextTool,
)
from src.application.use_case.build_ticker_sector_context_use_case import (
    BuildTickerSectorContextRequest,
    SectorMacroContextFacts,
    SectorMacroFactorFact,
    SectorPeerContextFacts,
    TickerSectorContextResult,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


class _FakeUc:
    def __init__(self, result: TickerSectorContextResult | None) -> None:
        self.result = result
        self.calls: list[BuildTickerSectorContextRequest] = []

    def execute(self, request: BuildTickerSectorContextRequest):
        self.calls.append(request)
        return self.result


def _full_result() -> TickerSectorContextResult:
    return TickerSectorContextResult(
        ticker="BBCA",
        as_of=date(2026, 8, 1),
        sector_group="bank",
        peer_context=SectorPeerContextFacts(
            sector_label="bank",
            peer_count=2,
            peer_tickers=("BBRI", "BMRI"),
            sector_20d_return=0.02,
            sector_vs_ihsg_20d=0.01,
            sector_breadth=0.5,
            ticker_vs_sector_rs=0.0,
            sector_regime="NEUTRAL",
        ),
        macro_context=SectorMacroContextFacts(
            sector_group="bank",
            macro_regime="SUPPORTIVE",
            factors=(
                SectorMacroFactorFact(
                    name="fx",
                    series="USDIDR",
                    value=0.0,
                    label="FAVORABLE",
                    rationale="ok",
                ),
            ),
        ),
        warnings=(),
    )


def test_definition_facts_not_verdict() -> None:
    tool = TickerSectorContextTool(_FakeUc(None))  # type: ignore[arg-type]
    assert tool.definition.name is AgentToolName.GET_TICKER_SECTOR_CONTEXT
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert (
        "verdict" in tool.definition.description.lower()
        or "not" in tool.definition.description.lower()
    )


def test_happy_path() -> None:
    tool = TickerSectorContextTool(_FakeUc(_full_result()))  # type: ignore[arg-type]
    result = tool.execute(
        "s1",
        TickerSectorContextArguments("BBCA", None, 10),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, TickerSectorContextResultData)
    assert result.data.peer_context is not None
    assert result.data.macro_context is not None
    assert not hasattr(result.data.macro_context, "composite_score")
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_partial_when_one_dimension_missing() -> None:
    partial = TickerSectorContextResult(
        ticker="BBCA",
        as_of=date(2026, 8, 1),
        sector_group="bank",
        peer_context=_full_result().peer_context,
        macro_context=None,
        warnings=("SECTOR_MACRO_CONTEXT_UNAVAILABLE",),
    )
    tool = TickerSectorContextTool(_FakeUc(partial))  # type: ignore[arg-type]
    result = tool.execute(
        "p1",
        TickerSectorContextArguments("BBCA", date(2026, 8, 1), 5),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "SECTOR_MACRO_CONTEXT_UNAVAILABLE" in result.warnings


def test_unavailable() -> None:
    tool = TickerSectorContextTool(_FakeUc(None))  # type: ignore[arg-type]
    result = tool.execute(
        "u1",
        TickerSectorContextArguments("BBCA", None, 10),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None


def test_peers_cap_arg() -> None:
    fake = _FakeUc(_full_result())
    tool = TickerSectorContextTool(fake)  # type: ignore[arg-type]
    args = tool.build_arguments(("bbca", "", "25"))
    assert args.peers_limit == 10
    tool.execute("c", args, _context())
    assert fake.calls[0].peers_limit == 10
