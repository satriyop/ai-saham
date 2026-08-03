"""Profile C — Phase 2 closed tools (journey SSOT §4.2 C0–C8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.dto.accumulation_agent import AgentTurnRequest, AgentTurnStatus
from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import AgentToolExecutionStatus, AgentToolName
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_broker_desk_tool import BrokerDeskTool
from src.application.services.agent_ticker_dashboard_tool import TickerDashboardTool
from src.application.services.agent_visible_cockpit_tool import (
    VisibleCockpitResultArguments,
    VisibleCockpitResultTool,
)
from src.infrastructure.composition.agent_model import build_agent_composition
from src.infrastructure.composition.view_broker_deps import (
    build_read_only_broker_desk_use_cases,
)
from src.infrastructure.composition.view_ticker_deps import (
    build_read_only_ticker_dashboard_use_case,
)
from src.infrastructure.config.app_config import AiConfig
from tests.agent_live.conftest import (
    action_identity,
    agent_live_call,
    assert_tool_trace_closed,
    live_broker,
    live_ticker,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = [pytest.mark.agent, agent_live_call]

_CLOSED = {
    AgentToolName.GET_VISIBLE_COCKPIT_RESULT,
    AgentToolName.GET_TICKER_DASHBOARD,
    AgentToolName.JUDGE_ACCUMULATION_TICKER,
    AgentToolName.GET_BROKER_DESK,
}


def test_c0_composition_registers_tool_subset(
    require_deepseek_key: str,
    live_db_path: Path,
) -> None:
    """C0: tools_enabled + DB registers expected ADR-061 subset."""
    del require_deepseek_key
    composition = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True),
        db_path=live_db_path,
    )
    assert composition.tools_enabled is True
    assert AgentToolName.GET_VISIBLE_COCKPIT_RESULT in composition.registered_tools
    for name in composition.registered_tools:
        assert name in _CLOSED


def test_c8_tools_off_no_tool_definitions_path(require_deepseek_key: str) -> None:
    """C8: tools off → no tool registry activation."""
    del require_deepseek_key
    composition = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=False),
    )
    assert composition.tools_enabled is False
    assert composition.registered_tools == ()


def test_c1_get_visible_cockpit_result_live_path(live_candidate) -> None:
    """Direct live path for get_visible_cockpit_result (always cache-free)."""
    ctx = AgentToolExecutionContext(
        visible_accumulation_context=build_agent_accumulation_context(live_candidate)
    )
    tool = VisibleCockpitResultTool()
    result = tool.execute(
        "live-visible-1",
        VisibleCockpitResultArguments(ctx.visible_accumulation_context.context_reference),
        ctx,
    )
    assert tool.definition.name is AgentToolName.GET_VISIBLE_COCKPIT_RESULT
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert result.result_reference.startswith("sha256:")


def test_c2_get_ticker_dashboard_cache_path(live_db_path: Path) -> None:
    """Direct live path for get_ticker_dashboard against local cache."""
    try:
        dashboard_uc = build_read_only_ticker_dashboard_use_case(live_db_path)
    except (OSError, ValueError) as exc:
        pytest.skip(f"ticker dashboard use case unavailable: {exc}")
    tool = TickerDashboardTool(dashboard_uc)
    ctx = AgentToolExecutionContext(
        visible_accumulation_context=build_agent_accumulation_context(make_candidate())
    )
    ticker = live_ticker()
    args = tool.build_arguments((ticker,))
    result = tool.execute("live-dash-1", args, ctx)
    assert tool.definition.name is AgentToolName.GET_TICKER_DASHBOARD
    assert result.status in {
        AgentToolExecutionStatus.SUCCESS,
        AgentToolExecutionStatus.PARTIAL,
        AgentToolExecutionStatus.UNAVAILABLE,
        AgentToolExecutionStatus.FAILED,
    }
    if result.status in {
        AgentToolExecutionStatus.SUCCESS,
        AgentToolExecutionStatus.PARTIAL,
    }:
        assert result.result_reference.startswith("sha256:")
        schema = getattr(result.data, "schema_id", "")
        assert "ticker_dashboard" in schema or schema.startswith("agent_tool.")


def test_c4_get_broker_desk_show_cache_path(live_db_path: Path) -> None:
    """Direct live path for get_broker_desk SHOW against local cache."""
    try:
        desk = build_read_only_broker_desk_use_cases(live_db_path)
    except (OSError, ValueError) as exc:
        pytest.skip(f"broker desk use cases unavailable: {exc}")
    tool = BrokerDeskTool(desk)
    ctx = AgentToolExecutionContext(
        visible_accumulation_context=build_agent_accumulation_context(make_candidate())
    )
    code = live_broker()
    args = tool.build_arguments((code, "SHOW"))
    result = tool.execute("live-desk-1", args, ctx)
    assert tool.definition.name is AgentToolName.GET_BROKER_DESK
    assert result.status in {
        AgentToolExecutionStatus.SUCCESS,
        AgentToolExecutionStatus.UNAVAILABLE,
        AgentToolExecutionStatus.FAILED,
    }
    if result.status is AgentToolExecutionStatus.SUCCESS:
        assert result.result_reference.startswith("sha256:")


def test_c3_judge_accumulation_ticker_direct_execute(
    live_db_path: Path,
    live_candidate,
) -> None:
    """C3: direct AccumulationJudgeTool.execute against local read-only screen path.

    Mirrors c1/c2/c4: does not depend on the model choosing to call the tool.
    Skips when factory/cache path is unavailable.
    """
    from src.adapters.composition.screen_deps import (
        build_read_only_accumulation_judge_runner,
    )
    from src.application.services.agent_accumulation_judge_tool import (
        AccumulationJudgeTool,
    )

    try:
        judge_runner = build_read_only_accumulation_judge_runner(
            live_db_path,
            universe="lq45",
        )
    except Exception as exc:  # noqa: BLE001 — live env may lack full screen deps
        pytest.skip(f"accumulation judge runner unavailable: {exc}")

    tool = AccumulationJudgeTool(judge_runner)
    assert tool.definition.name is AgentToolName.JUDGE_ACCUMULATION_TICKER
    ctx = AgentToolExecutionContext(
        visible_accumulation_context=build_agent_accumulation_context(live_candidate)
    )
    before = action_identity(live_candidate)
    ticker = live_ticker()
    args = tool.build_arguments((ticker,))
    result = tool.execute("live-judge-1", args, ctx)
    assert action_identity(live_candidate) == before
    assert result.status in {
        AgentToolExecutionStatus.SUCCESS,
        AgentToolExecutionStatus.PARTIAL,
        AgentToolExecutionStatus.UNAVAILABLE,
        AgentToolExecutionStatus.FAILED,
    }
    if result.status in {
        AgentToolExecutionStatus.SUCCESS,
        AgentToolExecutionStatus.PARTIAL,
    }:
        assert result.result_reference.startswith("sha256:")
        schema = getattr(result.data, "schema_id", "")
        assert "accum" in schema or schema.startswith("agent_tool.")


def test_c3_judge_registered_in_composition_when_factory_present(
    require_deepseek_key: str,
    live_db_path: Path,
) -> None:
    """C3 composition: factory registers judge tool in closed ADR-061 set."""
    del require_deepseek_key
    from src.adapters.composition.screen_deps import (
        build_read_only_accumulation_judge_runner,
    )

    try:
        composition = build_agent_composition(
            AiConfig(enabled=True, provider="deepseek", tools_enabled=True),
            db_path=live_db_path,
            accumulation_judge_factory=lambda: build_read_only_accumulation_judge_runner(
                live_db_path,
                universe="lq45",
            ),
        )
    except Exception as exc:  # noqa: BLE001 — live env may lack full screen deps
        pytest.skip(f"accumulation judge factory unavailable: {exc}")

    if AgentToolName.JUDGE_ACCUMULATION_TICKER not in composition.registered_tools:
        pytest.skip("judge_accumulation_ticker not registered in composition")
    for name in composition.registered_tools:
        assert name in _CLOSED


def test_c5_c6_orchestrator_live_turn_schema_and_action(
    live_composition_tools,
    live_candidate,
) -> None:
    """C5–C6: live turn; tool trace closed if any; Action identity unchanged."""
    before = action_identity(live_candidate)
    result = live_composition_tools.use_case.execute(
        AgentTurnRequest(
            "Using only the visible Judge facts, why is Action WATCH?",
            live_candidate,
        )
    )
    assert action_identity(live_candidate) == before
    if result.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}:
        assert result.answer.strip()
        if result.tool_results:
            assert_tool_trace_closed(result.tool_results)
            for item in result.tool_results:
                assert item.result_reference.startswith("sha256:")


def test_c7_missing_db_fail_soft_no_schema_create(
    require_deepseek_key: str,
    tmp_path: Path,
) -> None:
    """C7: missing/empty DB → tools fail-soft; no DB create from agent path."""
    del require_deepseek_key
    missing = tmp_path / "does-not-exist.db"
    assert not missing.exists()
    composition = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", tools_enabled=True),
        db_path=missing,
    )
    # Visible tool always present; cache tools may be absent
    assert AgentToolName.GET_VISIBLE_COCKPIT_RESULT in composition.registered_tools
    assert not missing.exists(), "agent composition must not create missing DB files"
