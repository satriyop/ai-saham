"""Offline agent tests for get_ticker_ownership (ADR-061 closed read tool)."""

from __future__ import annotations

from dataclasses import dataclass, field
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
from src.application.services.agent_ticker_ownership_tool import (
    TickerOwnershipArguments,
    TickerOwnershipResultData,
    TickerOwnershipTool,
)
from src.domain.value_objects.shareholding_composition import ShareholdingComposition
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent

_REPORT_DATE = date(2026, 5, 29)


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _composition(
    *,
    report_date: date | None = _REPORT_DATE,
    institution_pct: float = 40.0,
    individual_pct: float = 25.0,
    top_holder_name: str = "DWIMURIA INVESTAMA ANDALAN",
    top_holder_pct: float = 35.0,
    total_shares: int | None = 123_275_050_000,
    total_shares_formatted: str | None = "123.28 B",
) -> ShareholdingComposition:
    return ShareholdingComposition(
        ticker="BBCA",
        report_date=report_date,
        institution_pct=institution_pct,
        individual_pct=individual_pct,
        top_holder_name=top_holder_name,
        top_holder_pct=top_holder_pct,
        total_shares=total_shares,
        total_shares_formatted=total_shares_formatted,
    )


@dataclass
class _FakeOwnershipSource:
    result: ShareholdingComposition | None
    calls: list[str] = field(default_factory=list)
    raises: bool = False

    def get_ownership(self, ticker: str) -> ShareholdingComposition | None:
        self.calls.append(ticker)
        if self.raises:
            raise RuntimeError("boom")
        return self.result


def test_definition_is_closed_read_none_approval() -> None:
    tool = TickerOwnershipTool(_FakeOwnershipSource(None))
    assert tool.definition.name is AgentToolName.GET_TICKER_OWNERSHIP
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert tool.definition.approval.value == "NONE"
    assert (
        "score" not in tool.definition.description.lower()
        or "not a" in tool.definition.description.lower()
    )


def test_happy_path_full_composition() -> None:
    fake = _FakeOwnershipSource(_composition())
    tool = TickerOwnershipTool(fake)
    result = tool.execute("own-1", TickerOwnershipArguments("BBCA"), _context())
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, TickerOwnershipResultData)
    assert result.data.ticker == "BBCA"
    assert result.data.report_date == _REPORT_DATE
    assert result.data.institution_pct == 40.0
    assert result.data.individual_pct == 25.0
    assert result.data.top_holder_name == "DWIMURIA INVESTAMA ANDALAN"
    assert result.data.top_holder_pct == 35.0
    assert result.data.total_shares == 123_275_050_000
    assert result.data.total_shares_formatted == "123.28 B"
    assert fake.calls == ["BBCA"]
    assert result.serialized_size() <= tool.definition.max_result_bytes
    # No score-like fields on result
    assert not hasattr(result.data, "score")
    assert not hasattr(result.data, "strength")
    assert not hasattr(result.data, "quality")
    assert not hasattr(result.data, "free_float_pct")


def test_missing_cache_is_unavailable() -> None:
    tool = TickerOwnershipTool(_FakeOwnershipSource(None))
    result = tool.execute("miss", TickerOwnershipArguments("BBCA"), _context())
    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None
    assert result.error_code == "TICKER_OWNERSHIP_UNAVAILABLE"


def test_read_failure_is_failed() -> None:
    tool = TickerOwnershipTool(_FakeOwnershipSource(None, raises=True))
    result = tool.execute("fail", TickerOwnershipArguments("BBCA"), _context())
    assert result.status is AgentToolExecutionStatus.FAILED
    assert result.data is None
    assert result.error_code == "TICKER_OWNERSHIP_READ_FAILED"
    assert result.retryable is False


def test_partial_when_top_holder_missing() -> None:
    composition = _composition(top_holder_name="", top_holder_pct=0.0)
    tool = TickerOwnershipTool(_FakeOwnershipSource(composition))
    result = tool.execute("th", TickerOwnershipArguments("BBCA"), _context())
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "TOP_HOLDER_UNAVAILABLE" in result.warnings
    assert isinstance(result.data, TickerOwnershipResultData)
    assert result.data.top_holder_name == ""


def test_partial_when_total_shares_missing() -> None:
    composition = _composition(total_shares=None, total_shares_formatted=None)
    tool = TickerOwnershipTool(_FakeOwnershipSource(composition))
    result = tool.execute("ts", TickerOwnershipArguments("BBCA"), _context())
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "TOTAL_SHARES_UNAVAILABLE" in result.warnings


def test_partial_when_report_date_missing() -> None:
    composition = _composition(report_date=None)
    tool = TickerOwnershipTool(_FakeOwnershipSource(composition))
    result = tool.execute("rd", TickerOwnershipArguments("BBCA"), _context())
    assert result.status is AgentToolExecutionStatus.PARTIAL
    assert "REPORT_DATE_UNAVAILABLE" in result.warnings
    assert result.data is not None
    assert result.data.report_date is None
    assert result.freshness is not None
    assert result.freshness.as_of is None


def test_argument_ticker_validation_and_normalization() -> None:
    tool = TickerOwnershipTool(_FakeOwnershipSource(None))
    args = tool.build_arguments(("bbca",))
    assert args.ticker == "BBCA"
    with pytest.raises(ValueError):
        tool.build_arguments(("TOO_LONG_TICKER",))
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", "extra"))
