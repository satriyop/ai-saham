"""Offline agent tests for get_ticker_research_brief."""

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
from src.application.services.agent_ticker_research_brief_tool import (
    TickerResearchBriefArguments,
    TickerResearchBriefResultData,
    TickerResearchBriefTool,
)
from src.application.use_case.build_ticker_research_brief_use_case import (
    SECTION_FOREIGN_FLOW,
    SECTION_REGIME,
    STATUS_PARTIAL,
    STATUS_SUCCESS,
    BriefForeignFlowFacts,
    BriefRegimeFacts,
    BriefSectionMeta,
    BuildTickerResearchBriefRequest,
    TickerResearchBriefResult,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


class _FakeUc:
    def __init__(self, result: TickerResearchBriefResult) -> None:
        self.result = result
        self.calls: list[BuildTickerResearchBriefRequest] = []

    def execute(self, request: BuildTickerResearchBriefRequest) -> TickerResearchBriefResult:
        self.calls.append(request)
        return self.result


def _brief(
    *,
    overall: str = STATUS_SUCCESS,
    warnings: tuple[str, ...] = (),
) -> TickerResearchBriefResult:
    foreign = BriefForeignFlowFacts(
        as_of=date(2026, 8, 1),
        days=5,
        cumulative_net_idr="100",
        latest_net_idr="20",
        net_buy_sessions=3,
        active_sessions=5,
        trend_direction="rising",
        resolved_source="stockbit",
    )
    regime = BriefRegimeFacts(
        as_of=date(2026, 8, 1),
        regime="RISK_ON",
        conviction=0.7,
        regime_confidence=0.5,
        signal_multiplier=1.0,
        gate_tightening=False,
        regime_stability="STABLE",
        days_in_regime=3,
        cohort_id="sha256:x",
        factors=(),
    )
    return TickerResearchBriefResult(
        schema_id="application.ticker_research_brief.v1",
        ticker="BBCA",
        as_of=date(2026, 8, 1),
        sections_requested=(SECTION_FOREIGN_FLOW, SECTION_REGIME),
        overall_status=overall,
        warnings=warnings,
        section_meta=(
            BriefSectionMeta(
                name=SECTION_FOREIGN_FLOW,
                status=STATUS_SUCCESS,
                as_of=date(2026, 8, 1),
            ),
            BriefSectionMeta(
                name=SECTION_REGIME,
                status=STATUS_SUCCESS,
                as_of=date(2026, 8, 1),
            ),
        ),
        judge=None,
        broker_flow=None,
        foreign_flow=foreign,
        ownership=None,
        corporate_actions=None,
        regime=regime,
    )


def test_definition_facts_not_verdict() -> None:
    tool = TickerResearchBriefTool(_FakeUc(_brief()))
    assert tool.definition.name is AgentToolName.GET_TICKER_RESEARCH_BRIEF
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    desc = tool.definition.description.lower()
    assert "facts only" in desc
    assert "verdict" in desc


def test_happy_path() -> None:
    tool = TickerResearchBriefTool(_FakeUc(_brief()))
    result = tool.execute(
        "b1",
        TickerResearchBriefArguments("BBCA", None, (SECTION_FOREIGN_FLOW, SECTION_REGIME)),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, TickerResearchBriefResultData)
    assert result.data.foreign_flow is not None
    assert result.data.regime is not None
    forbidden = {"verdict", "brief_conclusion", "recommendation", "overall_action"}
    assert set(result.data.__dataclass_fields__).isdisjoint(forbidden)
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_partial_maps_status() -> None:
    brief = _brief(overall=STATUS_PARTIAL, warnings=("SECTION_JUDGE_UNAVAILABLE",))
    tool = TickerResearchBriefTool(_FakeUc(brief))
    result = tool.execute(
        "b2",
        TickerResearchBriefArguments("BBCA", None, (SECTION_FOREIGN_FLOW,)),
        _context(),
    )
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "SECTION_JUDGE_UNAVAILABLE" in result.warnings


def test_build_arguments() -> None:
    tool = TickerResearchBriefTool(_FakeUc(_brief()))
    args = tool.build_arguments(("bbca", "2026-08-01", "regime,foreign_flow"))
    assert args.ticker == "BBCA"
    assert args.as_of == date(2026, 8, 1)
    assert args.sections == (SECTION_FOREIGN_FLOW, SECTION_REGIME)
