import pytest

from src.application.dto.accumulation_agent import (
    AgentModelResponse,
    AgentModelUnavailableReason,
    AgentTurnPolicy,
    AgentTurnStatus,
)
from src.application.ports.agent_model import (
    AgentModelAuthenticationError,
    AgentModelMalformedResponseError,
    AgentModelRateLimitError,
    AgentModelTimeoutError,
    AgentModelTransportError,
    AgentModelUnavailableError,
)
from src.application.services.agent_stage_context import build_judge_turn_request
from src.application.use_case.explain_accumulation_candidate_use_case import (
    ExplainAccumulationCandidateUseCase,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


class _Model:
    def __init__(self) -> None:
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return AgentModelResponse("Fakta tetap WATCH.", "deepseek", "deepseek-v4-flash")


def test_one_turn_projects_same_candidate_and_calls_model_once() -> None:
    model = _Model()
    use_case = ExplainAccumulationCandidateUseCase(
        model,
        AgentTurnPolicy(True, "deepseek"),
    )
    candidate = make_candidate()
    result = use_case.execute(build_judge_turn_request("Mengapa WATCH?", candidate))

    assert result.status is AgentTurnStatus.SUCCESS
    assert result.answer == "Fakta tetap WATCH."
    assert len(model.requests) == 1
    assert model.requests[0].context.trade_setup.action == "WATCH"


def test_disabled_agent_is_unavailable_without_model_call() -> None:
    use_case = ExplainAccumulationCandidateUseCase(
        None,
        AgentTurnPolicy(
            False,
            "deepseek",
            AgentModelUnavailableReason.DISABLED,
        ),
    )
    result = use_case.execute(build_judge_turn_request("why?", make_candidate()))
    assert result.status is AgentTurnStatus.UNAVAILABLE
    assert result.answer == ""


@pytest.mark.parametrize(
    "error",
    [
        AgentModelAuthenticationError(),
        AgentModelTimeoutError(),
        AgentModelRateLimitError(),
        AgentModelUnavailableError(),
        AgentModelMalformedResponseError(),
        AgentModelTransportError(),
    ],
)
def test_expected_provider_failures_are_operator_safe(error) -> None:
    class FailingModel:
        def generate(self, request):
            raise error

    use_case = ExplainAccumulationCandidateUseCase(
        FailingModel(), AgentTurnPolicy(True, "deepseek")
    )
    result = use_case.execute(build_judge_turn_request("why?", make_candidate()))
    assert result.status is AgentTurnStatus.FAILED
    assert result.answer == ""
    assert result.error_message
