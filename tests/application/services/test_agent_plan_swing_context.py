"""ADR-066 Slice 5: plan_swing structure desk context contract."""

from __future__ import annotations

import pytest

from src.application.dto.accumulation_agent import AgentStageKind
from src.application.services.agent_accumulation_context import (
    AgentContextUnavailableError,
)
from src.application.services.agent_plan_swing_context import (
    SCHEMA_ID,
    AgentPlanSwingRawInput,
    build_agent_plan_swing_context,
)
from src.application.services.agent_stage_context import build_agent_stage_context

pytestmark = pytest.mark.agent


def test_happy_path_geometry() -> None:
    raw = AgentPlanSwingRawInput(
        ticker="BBCA",
        action="WATCH",
        entry="9,100",
        stop="8,800",
        target="9,800",
        lots="2",
        risk_pct="1.0",
        horizon="swing",
        inherits_action=True,
        no_order=True,
        summary="structure WATCH · entry 9,100 · no order",
        board_kind="accum",
        board_action="WATCH",
        board_signal="72",
        board_accum="7.0",
        board_gate="—",
    )
    ctx = build_agent_plan_swing_context(raw)
    assert ctx.schema_id == SCHEMA_ID
    assert ctx.stage_kind is AgentStageKind.PLAN_SWING
    assert ctx.ticker == "BBCA"
    assert ctx.geometry_available is True
    assert ctx.no_order is True
    assert ctx.context_reference.startswith("sha256:")
    assert ctx.session_subject == "PLAN_SWING:BBCA"


def test_incomplete_structure_ok_with_note() -> None:
    raw = AgentPlanSwingRawInput(
        ticker="BBCA",
        action="WATCH",
        incomplete_reason="no capital · set swing.capital",
        summary="structure WATCH · sizing incomplete · no order",
    )
    ctx = build_agent_plan_swing_context(raw)
    assert ctx.geometry_available is False
    assert any("capital" in w or "incomplete" in w.lower() for w in ctx.warnings)


def test_running_unavailable() -> None:
    with pytest.raises(AgentContextUnavailableError, match="running"):
        build_agent_plan_swing_context(AgentPlanSwingRawInput(ticker="BBCA", running=True))


def test_empty_facts_unavailable() -> None:
    with pytest.raises(AgentContextUnavailableError, match="no structure"):
        build_agent_plan_swing_context(AgentPlanSwingRawInput(ticker="BBCA"))


def test_facade_dispatches() -> None:
    raw = AgentPlanSwingRawInput(
        ticker="BBCA",
        action="ENTER",
        entry="100",
        stop="90",
        target="120",
        lots="1",
        summary="ok",
    )
    via = build_agent_stage_context(AgentStageKind.PLAN_SWING, raw)
    direct = build_agent_plan_swing_context(raw)
    assert via.context_reference == direct.context_reference
