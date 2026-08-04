"""Offline agent tests for get_ticker_insider_activity (ADR-061 closed read tool,
coverage row 7)."""

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
from src.application.services.agent_ticker_insider_tool import (
    TickerInsiderActivityTool,
    TickerInsiderArguments,
    TickerInsiderResultData,
)
from src.domain.value_objects.insider_transaction import InsiderTransaction
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent

_TODAY = date(2026, 8, 4)


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _today() -> date:
    return _TODAY


def _txn(
    name: str,
    action_type: str,
    shares: int,
    transaction_date: date,
    *,
    price: float = 1000.0,
) -> InsiderTransaction:
    return InsiderTransaction(
        ticker="BBCA",
        name=name,
        role="DIREKTUR",
        action_type=action_type,
        shares=shares,
        price=price,
        transaction_date=transaction_date,
        ownership_before_pct=0.1,
        ownership_after_pct=0.2,
    )


@dataclass
class _Call:
    ticker: str
    from_date: date
    to_date: date
    action_type: str
    as_of_date: date | None


@dataclass
class _FakeSource:
    all_transactions: list[InsiderTransaction] = field(default_factory=list)
    calls: list[_Call] = field(default_factory=list)
    raise_on_call_index: int | None = None

    def get_insider_transactions(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        action_type: str = "BUY",
        as_of_date: date | None = None,
    ) -> list[InsiderTransaction]:
        call_index = len(self.calls)
        self.calls.append(_Call(ticker, from_date, to_date, action_type, as_of_date))
        if self.raise_on_call_index == call_index:
            raise RuntimeError("boom")
        return [
            t
            for t in self.all_transactions
            if t.ticker == ticker and from_date <= t.transaction_date <= to_date
        ]


def test_definition_is_closed_read_none_approval() -> None:
    tool = TickerInsiderActivityTool(_FakeSource(), today=_today)
    assert tool.definition.name is AgentToolName.GET_TICKER_INSIDER_ACTIVITY
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert tool.definition.approval.value == "NONE"
    assert "enter" not in tool.definition.description.lower()
    assert "skip" not in tool.definition.description.lower()


def test_happy_path_mixed_buy_sell() -> None:
    source = _FakeSource(
        all_transactions=[
            _txn("SANTOSO", "BUY", 100_000, date(2026, 8, 1)),
            _txn("WIJAYA", "SELL", 40_000, date(2026, 7, 20)),
        ]
    )
    tool = TickerInsiderActivityTool(source, today=_today)
    out = tool.execute("h-1", TickerInsiderArguments("BBCA", 90, 20), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(out.data, TickerInsiderResultData)
    assert out.data.ticker == "BBCA"
    assert out.data.as_of == date(2026, 8, 1)
    assert out.data.window_transaction_count == 2
    assert len(out.data.transactions) == 2
    assert out.data.transactions[0].name == "SANTOSO"  # newest first
    assert out.data.buy_count == 1
    assert out.data.sell_count == 1
    assert out.data.net_shares == 60_000
    assert out.data.net_buy_ratio == pytest.approx(60_000 / 140_000)
    assert out.warnings == ()
    assert out.serialized_size() <= tool.definition.max_result_bytes
    assert not hasattr(out.data, "action")
    assert not hasattr(out.data, "verdict")


def test_calls_pass_action_type_all_and_explicit_as_of_date() -> None:
    """The core read-only guardrail: never rely on the port's own BUY-only/live
    default — always request ALL and pin as_of_date so the read is provably
    cache-only regardless of how the injected source's api_client is wired."""
    source = _FakeSource()
    tool = TickerInsiderActivityTool(source, today=_today)
    tool.execute("c-1", TickerInsiderArguments("BBCA", 90, 20), _context())

    assert len(source.calls) == 2  # primary window + ever_fetched fallback
    for call in source.calls:
        assert call.action_type == "ALL"
        assert call.as_of_date == _TODAY
    assert source.calls[0].from_date == date(2026, 5, 6)
    assert source.calls[0].to_date == _TODAY


def test_limit_truncates_and_flags_info() -> None:
    source = _FakeSource(
        all_transactions=[
            _txn("A", "BUY", 1_000, date(2026, 8, 1)),
            _txn("B", "BUY", 2_000, date(2026, 7, 30)),
            _txn("C", "SELL", 500, date(2026, 7, 29)),
        ]
    )
    tool = TickerInsiderActivityTool(source, today=_today)
    out = tool.execute("t-1", TickerInsiderArguments("BBCA", 90, 2), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert out.data.window_transaction_count == 3
    assert len(out.data.transactions) == 2
    assert "TRUNCATED_TO_LIMIT" in out.warnings
    # Summary reflects the full window, not just the capped/returned rows.
    assert out.data.buy_count == 2
    assert out.data.sell_count == 1


def test_empty_window_with_older_activity_is_success_with_info() -> None:
    source = _FakeSource(
        all_transactions=[_txn("OLD", "BUY", 10_000, date(2024, 1, 1))],
    )
    tool = TickerInsiderActivityTool(source, today=_today)
    out = tool.execute("e-1", TickerInsiderArguments("BBCA", 90, 20), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert "NO_INSIDER_ACTIVITY_IN_WINDOW" in out.warnings
    assert out.data.window_transaction_count == 0
    assert out.data.transactions == ()
    assert out.data.as_of is None


def test_never_fetched_is_unavailable() -> None:
    source = _FakeSource(all_transactions=[])
    tool = TickerInsiderActivityTool(source, today=_today)
    out = tool.execute("u-1", TickerInsiderArguments("BBCA", 90, 20), _context())

    assert out.status is AgentToolExecutionStatus.UNAVAILABLE
    assert out.data is None
    assert out.error_code == "TICKER_INSIDER_UNAVAILABLE"


def test_read_failure_on_primary_window_is_failed() -> None:
    source = _FakeSource(raise_on_call_index=0)
    tool = TickerInsiderActivityTool(source, today=_today)
    out = tool.execute("f-1", TickerInsiderArguments("BBCA", 90, 20), _context())

    assert out.status is AgentToolExecutionStatus.FAILED
    assert out.error_code == "TICKER_INSIDER_READ_FAILED"
    assert out.retryable is False


def test_read_failure_on_ever_fetched_fallback_is_failed() -> None:
    source = _FakeSource(raise_on_call_index=1)
    tool = TickerInsiderActivityTool(source, today=_today)
    out = tool.execute("f-2", TickerInsiderArguments("BBCA", 90, 20), _context())

    assert out.status is AgentToolExecutionStatus.FAILED
    assert out.error_code == "TICKER_INSIDER_READ_FAILED"


def test_build_arguments_defaults_and_caps() -> None:
    tool = TickerInsiderActivityTool(_FakeSource(), today=_today)
    args = tool.build_arguments(("bbca", "", ""))
    assert args.ticker == "BBCA"
    assert args.window_days == 90
    assert args.limit == 20

    capped = tool.build_arguments(("BBCA", "9999", "9999"))
    assert capped.window_days == 90
    assert capped.limit == 20


def test_build_arguments_rejects_bad_ticker_and_bad_ints() -> None:
    tool = TickerInsiderActivityTool(_FakeSource(), today=_today)
    with pytest.raises(ValueError):
        tool.build_arguments(("TOO_LONG", "", ""))
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", "not-a-number", ""))
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", "0", ""))


def test_argument_count_is_enforced() -> None:
    tool = TickerInsiderActivityTool(_FakeSource(), today=_today)
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", ""))
