from dataclasses import replace

import pytest

from src.application.dto.accumulation_agent import (
    AgentTurnRequest,
    AgentTurnResult,
    AgentTurnStatus,
)
from src.application.dto.agent_session import AgentSessionPolicy
from src.application.services.agent_session_store import InMemoryAgentSessionStore
from src.application.use_case.session_aware_agent_turn_use_case import (
    DEEPSEEK_SESSION_CERTIFICATION,
    SessionAwareAgentTurnUseCase,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


class _FakeInner:
    def __init__(self) -> None:
        self.calls = []
        self.provider_available = True
        self.configured_provider = "deepseek"

    def execute(self, request, *, is_cancelled=None, session_pack=None):
        del is_cancelled
        self.calls.append(session_pack)
        from src.application.services.agent_accumulation_context import (
            build_agent_accumulation_context,
        )

        context = build_agent_accumulation_context(request.candidate)
        return AgentTurnResult(
            status=AgentTurnStatus.SUCCESS,
            answer=f"answer for {request.user_text}",
            context_reference=context.context_reference,
            provider="deepseek",
            model="deepseek-v4-flash",
        )


def _session_uc(enabled: bool = True) -> tuple[SessionAwareAgentTurnUseCase, _FakeInner]:
    inner = _FakeInner()
    store = InMemoryAgentSessionStore(AgentSessionPolicy(enabled=enabled))
    uc = SessionAwareAgentTurnUseCase(
        inner,
        store,
        AgentSessionPolicy(enabled=enabled),
        certification=DEEPSEEK_SESSION_CERTIFICATION if enabled else None,
        configured_provider="deepseek",
    )
    return uc, inner


def test_disabled_session_never_packs_or_retains_state() -> None:
    uc, inner = _session_uc(enabled=False)
    candidate = make_candidate()
    first = uc.execute(AgentTurnRequest("why watch?", candidate))
    second = uc.execute(AgentTurnRequest("why risk?", candidate))
    assert first.status is AgentTurnStatus.SUCCESS
    assert second.status is AgentTurnStatus.SUCCESS
    assert first.session_id is None
    assert second.session_id is None
    assert inner.calls == [None, None]


def test_enabled_session_retains_follow_up_pack() -> None:
    uc, inner = _session_uc(enabled=True)
    candidate = make_candidate()
    first = uc.execute(AgentTurnRequest("why watch?", candidate))
    second = uc.execute(AgentTurnRequest("explain gate", candidate))
    assert first.session_id is not None
    assert first.turn_sequence == 1
    assert second.session_id == first.session_id
    assert second.turn_sequence == 2
    assert inner.calls[0] is not None
    assert inner.calls[0].next_turn_sequence == 1
    assert inner.calls[1] is not None
    assert inner.calls[1].next_turn_sequence == 2
    assert len(inner.calls[1].prior_commentary) == 1
    assert inner.calls[1].prior_commentary[0].question == "why watch?"


def test_max_turns_fails_closed() -> None:
    uc, _inner = _session_uc(enabled=True)
    candidate = make_candidate()
    for i in range(8):
        result = uc.execute(AgentTurnRequest(f"q{i}", candidate))
        assert result.status is AgentTurnStatus.SUCCESS
    blocked = uc.execute(AgentTurnRequest("q9", candidate))
    assert blocked.status is AgentTurnStatus.FAILED
    assert "maximum of 8 turns" in (blocked.error_message or "")


def test_reset_clears_session() -> None:
    uc, inner = _session_uc(enabled=True)
    candidate = make_candidate()
    first = uc.execute(AgentTurnRequest("first", candidate))
    new_id = uc.reset_session()
    second = uc.execute(AgentTurnRequest("after reset", candidate))
    assert new_id != first.session_id
    assert second.session_id == new_id
    assert second.turn_sequence == 1
    assert inner.calls[-1].prior_commentary == ()


def test_session_dedupes_repeated_data_warnings_across_turns() -> None:
    class _WarnInner:
        provider_available = True
        configured_provider = "deepseek"

        def execute(self, request, *, is_cancelled=None, session_pack=None):
            del is_cancelled, session_pack
            from src.application.services.agent_accumulation_context import (
                build_agent_accumulation_context,
            )

            context = build_agent_accumulation_context(request.candidate)
            return AgentTurnResult(
                status=AgentTurnStatus.SUCCESS,
                answer=f"answer for {request.user_text}",
                context_reference=context.context_reference,
                provider="deepseek",
                model="deepseek-v4-flash",
                warnings=(
                    "Risk snapshot 2026-07-31 differs from decision as-of 2026-08-01",
                    "SESSION_ALIGNED_LATE_WITHIN_LAG",
                ),
            )

    store = InMemoryAgentSessionStore(AgentSessionPolicy(enabled=True))
    uc = SessionAwareAgentTurnUseCase(
        _WarnInner(),
        store,
        AgentSessionPolicy(enabled=True),
        certification=DEEPSEEK_SESSION_CERTIFICATION,
        configured_provider="deepseek",
    )
    candidate = make_candidate()
    first = uc.execute(AgentTurnRequest("q1", candidate))
    second = uc.execute(AgentTurnRequest("q2", candidate))
    assert first.warnings
    assert any("Risk snapshot" in w for w in first.warnings)
    # Same data notes should not reappear on the next turn display payload.
    assert second.warnings == ()


def test_typeerror_in_inner_runs_exactly_once() -> None:
    """F1: a TypeError from the inner turn must NOT re-run the turn.

    The old retry ladder caught the TypeError and re-invoked ``execute`` with
    progressively fewer kwargs — re-running a turn that may already have spent
    the provider and dropping the approval callback. It now runs exactly once.
    """

    class _RaisingInner:
        provider_available = True
        configured_provider = "deepseek"

        def __init__(self) -> None:
            self.calls = 0

        def execute(self, request, **kwargs):
            self.calls += 1
            raise TypeError("boom during execution")

    inner = _RaisingInner()
    store = InMemoryAgentSessionStore(AgentSessionPolicy(enabled=True))
    uc = SessionAwareAgentTurnUseCase(
        inner,
        store,
        AgentSessionPolicy(enabled=True),
        certification=DEEPSEEK_SESSION_CERTIFICATION,
        configured_provider="deepseek",
    )
    with pytest.raises(TypeError):
        uc.execute(
            AgentTurnRequest("q", make_candidate()),
            on_progress=lambda _m: None,
            on_approval=lambda _r: True,
        )
    assert inner.calls == 1


def test_inner_without_callback_kwargs_still_invoked_once() -> None:
    """F1 boundary: signature probing (not error-catching) adapts to a narrow inner."""
    uc, inner = _session_uc(enabled=True)
    result = uc.execute(
        AgentTurnRequest("why watch?", make_candidate()),
        on_progress=lambda _m: None,
        on_approval=lambda _r: True,
    )
    # _FakeInner.execute accepts only is_cancelled/session_pack; the extra
    # callbacks are filtered out up front so it is called exactly once.
    assert result.status is AgentTurnStatus.SUCCESS
    assert len(inner.calls) == 1


def test_stale_focus_warning_when_context_changes() -> None:
    uc, inner = _session_uc(enabled=True)
    first_candidate = make_candidate()
    uc.execute(AgentTurnRequest("first", first_candidate))
    second_candidate = replace(
        first_candidate,
        trade_setup=replace(first_candidate.trade_setup, rationale="Different wait reason"),
    )
    result = uc.execute(AgentTurnRequest("second", second_candidate))
    assert result.status is AgentTurnStatus.SUCCESS
    pack = inner.calls[-1]
    assert pack is not None
    assert pack.prior_commentary
    assert pack.current_context_reference != pack.prior_commentary[0].context_reference
    assert any("changed" in w.lower() or "historical" in w.lower() for w in pack.pack_warnings)
