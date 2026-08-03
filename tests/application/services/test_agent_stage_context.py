"""ADR-066 Slice 0: stage facade, bit-identical Judge hash, single-build discipline."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.application.dto.accumulation_agent import (
    AgentModelResponse,
    AgentStageKind,
    AgentTurnPolicy,
    AgentTurnStatus,
)
from src.application.dto.agent_session import AgentSessionPolicy
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_session_store import InMemoryAgentSessionStore
from src.application.services.agent_stage_context import (
    build_agent_stage_context,
    build_judge_turn_request,
)
from src.application.use_case.explain_accumulation_candidate_use_case import (
    ExplainAccumulationCandidateUseCase,
)
from src.application.use_case.session_aware_agent_turn_use_case import (
    DEEPSEEK_SESSION_CERTIFICATION,
    SessionAwareAgentTurnUseCase,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def test_judge_facade_matches_direct_builder_hash() -> None:
    candidate = make_candidate()
    direct = build_agent_accumulation_context(candidate)
    via_facade = build_agent_stage_context(AgentStageKind.ACCUM_JUDGE, candidate)
    assert via_facade.schema_id == "tui_agent.accum_judge.v1"
    assert via_facade.stage_kind is AgentStageKind.ACCUM_JUDGE
    assert via_facade.context_reference == direct.context_reference
    assert via_facade.canonical_payload() == direct.canonical_payload()


def test_unshipped_stage_raises_unavailable() -> None:
    # All catalog stages are shipped; wrong-type still raises TypeError, not Unavailable.
    with pytest.raises(TypeError, match="plan_swing"):
        build_agent_stage_context(AgentStageKind.PLAN_SWING, object())


def test_wrong_raw_input_type_for_judge() -> None:
    with pytest.raises(TypeError, match="AccumulationCandidate"):
        build_agent_stage_context(AgentStageKind.ACCUM_JUDGE, "BBCA")


def test_consumers_do_not_rebuild_context() -> None:
    """Finding 5: consumers use built context; builder runs only via facade once."""

    class _Model:
        def generate(self, request):
            return AgentModelResponse(
                "Fakta WATCH.",
                "deepseek",
                "deepseek-v4-flash",
            )

    candidate = make_candidate()
    with patch(
        "src.application.services.agent_stage_context.build_agent_accumulation_context",
        wraps=build_agent_accumulation_context,
    ) as builder:
        request = build_judge_turn_request("why?", candidate)
        assert builder.call_count == 1

        phase1 = ExplainAccumulationCandidateUseCase(
            _Model(),
            AgentTurnPolicy(True, "deepseek"),
        )
        store = InMemoryAgentSessionStore(AgentSessionPolicy(enabled=True))
        uc = SessionAwareAgentTurnUseCase(
            phase1,
            store,
            AgentSessionPolicy(enabled=True),
            certification=DEEPSEEK_SESSION_CERTIFICATION,
            configured_provider="deepseek",
        )
        result = uc.execute(request)
        assert result.status is AgentTurnStatus.SUCCESS
        assert result.context_reference == request.stage_context.context_reference
        # No additional builds inside session_aware or explain.
        assert builder.call_count == 1


def test_judge_turn_request_carries_built_stage_context() -> None:
    candidate = make_candidate()
    request = build_judge_turn_request("hello", candidate)
    assert request.user_text == "hello"
    assert request.stage_context.stage_kind is AgentStageKind.ACCUM_JUDGE
    assert request.stage_context.context_reference.startswith("sha256:")
