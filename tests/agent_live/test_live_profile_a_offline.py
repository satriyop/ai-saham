"""Profile A — Offline / AI off (journey SSOT §4.0 A1–A4).

Under agent-live-call: still opt-in via AI_SAHAM_AGENT_LIVE, but never calls
the provider. Proves composition and cockpit path with AI disabled.
"""

from __future__ import annotations

import asyncio

import pytest

from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.infrastructure.composition import agent_model as agent_model_mod
from src.infrastructure.composition.agent_model import build_agent_composition
from src.infrastructure.config.app_config import AiConfig
from tests.adapters.tui.test_finish_cockpit_slices import _accum_payload
from tests.agent_live.conftest import agent_live_call

pytestmark = [pytest.mark.agent, agent_live_call]


def test_a1_a4_ai_disabled_zero_provider_construct(monkeypatch) -> None:
    """A1/A4: enabled=false → DeepSeek client never constructed."""
    constructed: list[str] = []

    def _boom(key: str) -> object:
        constructed.append(key)
        raise AssertionError("DeepSeekAgentModel must not be built when AI disabled")

    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(agent_model_mod, "DeepSeekAgentModel", _boom)
    monkeypatch.setattr(agent_model_mod, "read_local_env_value", lambda _n: None)

    composition = build_agent_composition(AiConfig(enabled=False, provider="deepseek"))
    assert composition.provider_available is False
    assert composition.tools_enabled is False
    assert composition.session_enabled is False
    assert composition.registered_tools == ()
    assert constructed == []

    from src.application.dto.accumulation_agent import AgentTurnRequest, AgentTurnStatus
    from tests.application.services.test_agent_accumulation_context import make_candidate

    result = composition.use_case.execute(AgentTurnRequest("why is this WATCH?", make_candidate()))
    assert result.status is AgentTurnStatus.UNAVAILABLE
    assert constructed == []


def test_a2_a3_cockpit_usable_without_agent_runner() -> None:
    """A2/A3: accum board + Judge without agent; prompt chrome does not crash."""

    async def scenario() -> None:
        app = CockpitApp(
            accum_loader=_accum_payload,
            accum_controller=BoardController(_accum_payload),
            accum_presenter=AccumPresenter(),
            agent_turn_runner=None,
            agent_provider_available=False,
        )
        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "accum" and app._rows:
                    break
            assert app._stage == "accum"
            assert app._rows
            app._open_detail()
            await pilot.pause()
            assert app._stage == "detail"
            assert app._status_note in {"judge", "re-judging"}
            app._prompt_mode = "agent"
            app._submit_agent_turn("should not dispatch")
            await pilot.pause()
            app._invalidate_agent_turn()
            await pilot.pause()

    asyncio.run(scenario())


def test_a1_disabled_composition_ignores_tool_session_flags() -> None:
    """Structural: disabled AI never requests tools/session even if flags true."""
    composition = build_agent_composition(
        AiConfig(
            enabled=False,
            provider="deepseek",
            tools_enabled=True,
            session_enabled=True,
        )
    )
    assert composition.tools_requested is False
    assert composition.session_requested is False
    assert composition.tools_enabled is False
    assert composition.session_enabled is False
