"""Profile D — Phase 3 ephemeral sessions (journey SSOT §4.3 D1–D9)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.application.dto.accumulation_agent import AgentTurnStatus
from src.application.services.agent_stage_context import build_judge_turn_request
from src.application.use_case.session_aware_agent_turn_use_case import (
    SessionAwareAgentTurnUseCase,
)
from src.infrastructure.composition.agent_model import build_agent_composition
from src.infrastructure.config.app_config import AiConfig
from tests.agent_live.conftest import agent_live_call, assert_context_reference

pytestmark = [pytest.mark.agent, agent_live_call]


def test_d1_session_wrap_present_when_certified(
    live_composition_session,
) -> None:
    """D1: session_enabled wrap active for certified DeepSeek."""
    assert live_composition_session.session_enabled is True
    assert isinstance(live_composition_session.use_case, SessionAwareAgentTurnUseCase)
    assert live_composition_session.use_case.session_enabled is True


def test_d2_d3_two_sequential_turns_same_candidate(
    live_composition_session,
    live_candidate,
) -> None:
    """D2–D3: two live questions → session_id continuity, turn_sequence >= 2."""
    uc = live_composition_session.use_case
    first = uc.execute(build_judge_turn_request("Why is Action WATCH?", live_candidate))
    second = uc.execute(
        build_judge_turn_request(
            "In one sentence, what gate or rationale supports that?", live_candidate
        )
    )
    assert first.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}
    assert second.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}
    assert first.session_id is not None
    assert first.turn_sequence == 1
    assert second.session_id == first.session_id
    assert second.turn_sequence is not None and second.turn_sequence >= 2
    assert_context_reference(first.context_reference)
    assert_context_reference(second.context_reference)


def test_d4_context_change_pack_warnings_safe(
    live_composition_session,
    live_candidate,
) -> None:
    """D4: different context_reference still yields safe status (warnings allowed)."""
    uc = live_composition_session.use_case
    first = uc.execute(build_judge_turn_request("Summarize Action briefly.", live_candidate))
    assert first.status in {
        AgentTurnStatus.SUCCESS,
        AgentTurnStatus.PARTIAL,
        AgentTurnStatus.FAILED,
    }
    altered = replace(
        live_candidate,
        trade_setup=replace(
            live_candidate.trade_setup,
            rationale="Different wait reason for context identity change",
        ),
    )
    second = uc.execute(build_judge_turn_request("Has context changed?", altered))
    assert second.status in {
        AgentTurnStatus.SUCCESS,
        AgentTurnStatus.PARTIAL,
        AgentTurnStatus.FAILED,
        AgentTurnStatus.UNAVAILABLE,
    }
    # Safe: no crash; session may continue with warnings (observed via status/answer)
    if second.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}:
        assert second.answer.strip()


def test_d5_d6_reset_session_new_sequence(
    live_composition_session,
    live_candidate,
) -> None:
    """D5–D6: reset_session → next turn sequence 1 with new session_id."""
    uc = live_composition_session.use_case
    first = uc.execute(build_judge_turn_request("First turn before reset.", live_candidate))
    assert first.session_id is not None
    new_id = uc.reset_session()
    assert new_id
    assert new_id != first.session_id
    after = uc.execute(build_judge_turn_request("After reset — start fresh.", live_candidate))
    assert after.session_id == new_id
    assert after.turn_sequence == 1


def test_d8_session_disabled_no_continuity(
    require_deepseek_key: str,
    live_candidate,
) -> None:
    """D8: session_enabled false → no session_id continuity."""
    del require_deepseek_key
    composition = build_agent_composition(
        AiConfig(enabled=True, provider="deepseek", session_enabled=False),
    )
    assert composition.session_enabled is False
    first = composition.use_case.execute(build_judge_turn_request("q1", live_candidate))
    second = composition.use_case.execute(build_judge_turn_request("q2", live_candidate))
    assert getattr(first, "session_id", None) in {None}
    assert getattr(second, "session_id", None) in {None}


def test_d9_non_deepseek_no_certified_session(monkeypatch) -> None:
    """D9: non-deepseek provider → no certified multi-turn session wrap."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-used-for-openai")
    composition = build_agent_composition(
        AiConfig(
            enabled=True,
            provider="openai",
            tools_enabled=True,
            session_enabled=True,
        ),
        provider="openai",
    )
    assert composition.configured_provider != "deepseek" or not composition.session_enabled
    assert composition.session_enabled is False
    assert not isinstance(composition.use_case, SessionAwareAgentTurnUseCase)


def test_d7_in_memory_store_process_local_note() -> None:
    """D7: document process-local memory — store is InMemoryAgentSessionStore."""
    from src.application.services.agent_session_store import InMemoryAgentSessionStore

    assert InMemoryAgentSessionStore.__module__.startswith("src.application")
