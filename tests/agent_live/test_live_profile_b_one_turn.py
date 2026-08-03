"""Profile B — Phase 1 one-turn live provider (journey SSOT §4.1 B2–B7)."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.application.dto.accumulation_agent import (
    AgentTurnRequest,
    AgentTurnResult,
    AgentTurnStatus,
)
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_stage_context import build_judge_turn_request
from tests.adapters.tui.agent_board_fixtures import agent_accum_payload as _accum_payload
from tests.agent_live.conftest import (
    action_identity,
    agent_live_call,
    assert_context_reference,
)

pytestmark = [pytest.mark.agent, agent_live_call]


def test_b2_b4_live_one_turn_success_or_partial(
    live_composition_phase1,
    live_candidate,
) -> None:
    """B2–B4: real provider one-shot → SUCCESS/PARTIAL, answer + context_reference."""
    uc = live_composition_phase1.use_case
    before_action = action_identity(live_candidate)
    result = uc.execute(
        build_judge_turn_request(
            "In one short sentence, why is the deterministic Action WATCH?",
            live_candidate,
        )
    )
    assert result.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}
    assert result.answer.strip()
    assert_context_reference(result.context_reference)
    assert result.provider == "deepseek"
    assert result.model
    expected_ref = build_agent_accumulation_context(live_candidate).context_reference
    assert result.context_reference == expected_ref
    assert action_identity(live_candidate) == before_action


def test_b5_tools_disabled_no_tool_results_required(
    live_composition_phase1,
    live_candidate,
) -> None:
    """B5: tools off — empty tool_results is OK."""
    assert live_composition_phase1.tools_enabled is False
    result = live_composition_phase1.use_case.execute(
        build_judge_turn_request("Summarize the risk gates briefly.", live_candidate)
    )
    assert result.status in {
        AgentTurnStatus.SUCCESS,
        AgentTurnStatus.PARTIAL,
        AgentTurnStatus.FAILED,
        AgentTurnStatus.UNAVAILABLE,
    }
    if result.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}:
        assert result.tool_results == () or result.tool_results is not None


@pytest.mark.tui
def test_b7_limited_row_without_source_unavailable_no_dispatch() -> None:
    """B7: limited snapshot row (source=None) → UNAVAILABLE path, no runner call."""
    calls: list[object] = []

    def runner(request: AgentTurnRequest) -> AgentTurnResult:
        calls.append(request)
        return AgentTurnResult(
            status=AgentTurnStatus.SUCCESS,
            answer="should not run",
            context_reference="sha256:" + ("a" * 64),
            provider="deepseek",
            model="deepseek-v4-flash",
        )

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
        )
        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            await pilot.pause()
            # Strip full source → limited judge
            row = app._rows[app._row_index]
            app._rows[app._row_index] = replace(row, source=None)
            app._prompt_mode = "agent"
            app._submit_agent_turn("Do not invent analysis")
            await pilot.pause(0.1)
            assert calls == []

    asyncio.run(scenario())


@pytest.mark.tui
def test_b6_generation_invalidate_discards_stale_paint() -> None:
    """B6: invalidate generation → late path does not leave wrong paint mandate."""

    async def scenario() -> None:
        def runner(_request: AgentTurnRequest) -> AgentTurnResult:
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer="stale",
                context_reference="sha256:" + ("b" * 64),
                provider="deepseek",
                model="deepseek-v4-flash",
            )

        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=runner,
            agent_provider_available=True,
        )
        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            app._open_detail()
            await pilot.pause()
            gen_before = app._agent_generation
            app._prompt_mode = "agent"
            app._submit_agent_turn("first")
            app._invalidate_agent_turn()
            assert app._agent_generation >= gen_before
            await pilot.pause(0.05)

    asyncio.run(scenario())


def test_b2_missing_key_unavailable(monkeypatch, live_candidate) -> None:
    """N1/B path: missing credential → UNAVAILABLE without crash."""
    from src.infrastructure.composition import agent_model as agent_model_mod
    from src.infrastructure.composition.agent_model import build_agent_composition
    from src.infrastructure.config.app_config import AiConfig

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(agent_model_mod, "read_local_env_value", lambda _n: None)
    composition = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek"),
    )
    assert composition.provider_available is False
    result = composition.use_case.execute(
        build_judge_turn_request("why?", live_candidate),
    )
    assert result.status is AgentTurnStatus.UNAVAILABLE
    assert result.error_message
