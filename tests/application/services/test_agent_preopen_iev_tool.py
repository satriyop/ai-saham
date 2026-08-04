"""Offline agent tests for get_preopen_iev (ADR-061 closed read tool, coverage row 12)."""

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
from src.application.services.agent_preopen_iev_tool import (
    PreopenIevArguments,
    PreopenIevResultData,
    PreopenIevTool,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent

_TODAY = date(2026, 8, 4)


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


@dataclass
class _Row:
    ticker: str
    iev: int
    rank: int
    iep: int | None = None
    is_ncp_locked: int = 0


@dataclass
class _FakeSource:
    rows_by_date: dict[date, list[_Row]] = field(default_factory=dict)
    baseline_by_date: dict[date, dict[str, int]] = field(default_factory=dict)
    dates: list[date] = field(default_factory=list)
    raise_on_snapshot: bool = False
    raise_on_baseline: bool = False

    def get_snapshot(self, snapshot_date: date, top_n: int | None = None) -> list[_Row]:
        if self.raise_on_snapshot:
            raise RuntimeError("boom")
        return self.rows_by_date.get(snapshot_date, [])

    def ncp_baseline_iev(self, snapshot_date: date) -> dict[str, int]:
        if self.raise_on_baseline:
            raise RuntimeError("boom")
        return self.baseline_by_date.get(snapshot_date, {})

    def get_snapshot_dates(self) -> list[date]:
        return self.dates


def _today() -> date:
    return _TODAY


def test_definition_is_closed_read_none_approval() -> None:
    tool = PreopenIevTool(_FakeSource(), today=_today)
    assert tool.definition.name is AgentToolName.GET_PREOPEN_IEV
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert tool.definition.approval.value == "NONE"
    assert "enter" not in tool.definition.description.lower()
    assert "skip" not in tool.definition.description.lower()


def test_happy_path_with_baseline_move() -> None:
    d = date(2026, 8, 3)
    source = _FakeSource(
        rows_by_date={d: [_Row(ticker="BBCA", iev=7250, rank=1, iep=7200, is_ncp_locked=1)]},
        baseline_by_date={d: {"BBCA": 7000}},
    )
    tool = PreopenIevTool(source, today=_today)
    out = tool.execute("h-1", PreopenIevArguments("BBCA", d), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(out.data, PreopenIevResultData)
    assert out.data.ticker == "BBCA"
    assert out.data.session_date == d
    assert out.data.iev == 7250
    assert out.data.iep == 7200
    assert out.data.rank == 1
    assert out.data.is_ncp_locked is True
    assert out.data.locked_baseline_iev == 7000
    assert out.data.iev_move_since_lock == 250
    assert out.warnings == ()
    assert out.serialized_size() <= tool.definition.max_result_bytes
    assert not hasattr(out.data, "action")
    assert not hasattr(out.data, "verdict")


def test_zero_move_is_a_real_success_finding_not_missing_data() -> None:
    """A true 0 delta (price hasn't moved since lock) is a genuine SUCCESS fact,
    not treated as missing/partial data."""
    d = date(2026, 8, 3)
    source = _FakeSource(
        rows_by_date={d: [_Row(ticker="BBCA", iev=7000, rank=1, is_ncp_locked=1)]},
        baseline_by_date={d: {"BBCA": 7000}},
    )
    tool = PreopenIevTool(source, today=_today)
    out = tool.execute("z-1", PreopenIevArguments("BBCA", d), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert out.data.iev_move_since_lock == 0
    assert out.warnings == ()


def test_no_locked_baseline_is_success_with_info_note() -> None:
    d = date(2026, 8, 3)
    source = _FakeSource(
        rows_by_date={d: [_Row(ticker="BBCA", iev=7200, rank=1, is_ncp_locked=0)]},
        baseline_by_date={},
    )
    tool = PreopenIevTool(source, today=_today)
    out = tool.execute("n-1", PreopenIevArguments("BBCA", d), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert "NO_POST_LOCK_MOVE" in out.warnings
    assert out.data.locked_baseline_iev is None
    assert out.data.iev_move_since_lock is None
    assert out.data.is_ncp_locked is False


def test_ticker_absent_on_date_is_unavailable() -> None:
    d = date(2026, 8, 3)
    source = _FakeSource(rows_by_date={d: [_Row(ticker="BMRI", iev=5000, rank=1)]})
    tool = PreopenIevTool(source, today=_today)
    out = tool.execute("u-1", PreopenIevArguments("BBCA", d), _context())

    assert out.status is AgentToolExecutionStatus.UNAVAILABLE
    assert out.data is None
    assert out.error_code == "PREOPEN_IEV_UNAVAILABLE"


def test_no_snapshot_dates_at_all_is_unavailable() -> None:
    source = _FakeSource(dates=[])
    tool = PreopenIevTool(source, today=_today)
    out = tool.execute("u-2", PreopenIevArguments("BBCA", None), _context())

    assert out.status is AgentToolExecutionStatus.UNAVAILABLE
    assert out.data is None
    assert out.error_code == "PREOPEN_IEV_UNAVAILABLE"


def test_default_session_date_resolves_to_latest_cached_date() -> None:
    older, newer = date(2026, 8, 1), date(2026, 8, 3)
    source = _FakeSource(
        dates=[older, newer],
        rows_by_date={newer: [_Row(ticker="BBCA", iev=7200, rank=1)]},
        baseline_by_date={newer: {"BBCA": 7000}},
    )
    tool = PreopenIevTool(source, today=_today)
    out = tool.execute("d-1", PreopenIevArguments("BBCA", None), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert out.data.session_date == newer


def test_future_session_date_is_unavailable_not_a_turn_failure() -> None:
    """F3: a future session_date is a non-fatal typed UNAVAILABLE on this one
    tool call, never a turn-failing argument validation error."""
    future = date(2026, 8, 5)
    tool = PreopenIevTool(_FakeSource(), today=_today)
    out = tool.execute("f-3", PreopenIevArguments("BBCA", future), _context())

    assert out.status is AgentToolExecutionStatus.UNAVAILABLE
    assert out.data is None
    assert out.error_code == "SESSION_DATE_IN_FUTURE"


def test_read_failure_on_snapshot_is_failed() -> None:
    d = date(2026, 8, 3)
    source = _FakeSource(raise_on_snapshot=True)
    tool = PreopenIevTool(source, today=_today)
    out = tool.execute("f-1", PreopenIevArguments("BBCA", d), _context())

    assert out.status is AgentToolExecutionStatus.FAILED
    assert out.error_code == "PREOPEN_IEV_READ_FAILED"
    assert out.retryable is False


def test_read_failure_on_baseline_is_failed() -> None:
    d = date(2026, 8, 3)
    source = _FakeSource(
        rows_by_date={d: [_Row(ticker="BBCA", iev=7200, rank=1)]},
        raise_on_baseline=True,
    )
    tool = PreopenIevTool(source, today=_today)
    out = tool.execute("f-2", PreopenIevArguments("BBCA", d), _context())

    assert out.status is AgentToolExecutionStatus.FAILED
    assert out.error_code == "PREOPEN_IEV_READ_FAILED"


def test_build_arguments_defaults_empty_session_date_to_none() -> None:
    tool = PreopenIevTool(_FakeSource(), today=_today)
    args = tool.build_arguments(("bbca", ""))
    assert args.ticker == "BBCA"
    assert args.session_date is None


def test_build_arguments_parses_iso_session_date_without_future_check() -> None:
    """build_arguments only parses the date; the future check happens in execute()
    so a future date is a typed UNAVAILABLE, not a whole-turn preflight failure."""
    tool = PreopenIevTool(_FakeSource(), today=_today)
    args = tool.build_arguments(("BBCA", "2026-08-05"))
    assert args.session_date == date(2026, 8, 5)


def test_build_arguments_rejects_bad_ticker_and_malformed_date() -> None:
    tool = PreopenIevTool(_FakeSource(), today=_today)
    with pytest.raises(ValueError):
        tool.build_arguments(("TOO_LONG", ""))
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", "not-a-date"))


def test_argument_count_is_enforced() -> None:
    tool = PreopenIevTool(_FakeSource(), today=_today)
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA",))
