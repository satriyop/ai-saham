"""ADR-066 Slice 3: view_broker stage context contract."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.dto.accumulation_agent import AgentStageKind
from src.application.services.agent_accumulation_context import (
    AgentContextUnavailableError,
)
from src.application.services.agent_broker_desk_tool import project_broker_desk_from_result
from src.application.services.agent_stage_context import build_agent_stage_context
from src.application.services.agent_view_broker_context import (
    SCHEMA_ID,
    build_agent_view_broker_context,
    build_agent_view_broker_context_from_result,
)
from src.application.services.broker_desk_from_daily_flow import DeskTickerNet
from src.domain.entities.broker_flow import BrokerType

pytestmark = pytest.mark.agent


def _ticker_net(ticker: str, net: str) -> DeskTickerNet:
    value = Decimal(net)
    buy = value if value > 0 else Decimal("0")
    sell = -value if value < 0 else Decimal("0")
    return DeskTickerNet(
        ticker=ticker,
        net_value=value,
        net_lot=10 if value > 0 else -10,
        buy_value=buy,
        sell_value=sell,
        sessions=1,
    )


def _show_result():
    return SimpleNamespace(
        broker_code="YP",
        broker_name="YP Desk",
        broker_type=BrokerType.FOREIGN,
        as_of=date(2026, 8, 1),
        day_net_value=Decimal("1500"),
        day_net_lot=12,
        day_ticker_count=2,
        top_buy_stocks=(_ticker_net("BBCA", "1000"),),
        top_sell_stocks=(_ticker_net("TLKM", "-500"),),
        scope_note="Tracked desk activity only (broker_daily_flow)",
    )


def test_happy_path_from_show_page() -> None:
    ctx = build_agent_view_broker_context_from_result("show", _show_result())
    assert ctx.schema_id == SCHEMA_ID
    assert ctx.stage_kind is AgentStageKind.VIEW_BROKER
    assert ctx.broker_code == "YP"
    assert ctx.view == "SHOW"
    assert ctx.as_of == date(2026, 8, 1)
    assert ctx.show is not None
    assert ctx.context_reference.startswith("sha256:")
    assert ctx.session_subject == "BROKER:YP:SHOW"


def test_stable_hash() -> None:
    projected = project_broker_desk_from_result("SHOW", _show_result())
    assert projected is not None
    data, warnings, _ = projected
    a = build_agent_view_broker_context(data, warnings=warnings)
    b = build_agent_view_broker_context(data, warnings=warnings)
    assert a.context_reference == b.context_reference


def test_missing_result_unavailable() -> None:
    with pytest.raises(AgentContextUnavailableError, match="no cached"):
        build_agent_view_broker_context_from_result("show", None)


def test_facade_dispatches_tuple() -> None:
    with pytest.raises(AgentContextUnavailableError):
        build_agent_stage_context(AgentStageKind.VIEW_BROKER, ("show", None))
    direct = build_agent_view_broker_context_from_result("show", _show_result())
    via = build_agent_stage_context(AgentStageKind.VIEW_BROKER, ("show", _show_result()))
    assert via.context_reference == direct.context_reference
