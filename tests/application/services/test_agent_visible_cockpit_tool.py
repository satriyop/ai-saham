import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import AgentToolExecutionStatus, AgentToolName
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_visible_cockpit_tool import (
    VisibleCockpitResultArguments,
    VisibleCockpitResultData,
    VisibleCockpitResultTool,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(
        visible_accumulation_context=build_agent_accumulation_context(make_candidate())
    )


def test_exact_reference_returns_same_captured_context_object() -> None:
    execution_context = _context()
    visible = execution_context.visible_accumulation_context
    tool = VisibleCockpitResultTool()

    result = tool.execute(
        "call-visible",
        VisibleCockpitResultArguments(visible.context_reference),
        execution_context,
    )

    assert tool.definition.name is AgentToolName.GET_VISIBLE_COCKPIT_RESULT
    assert tool.definition.timeout_ms == 100
    assert tool.definition.max_result_bytes == 32 * 1024
    assert result.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(result.data, VisibleCockpitResultData)
    assert result.data.context is visible
    assert result.data.schema_id == "agent_tool.visible_cockpit.result.v1"
    assert result.source_reference == visible.context_reference
    assert result.provenance.source_reference == visible.context_reference
    assert result.serialized_size() <= tool.definition.max_result_bytes


def test_unequal_reference_is_unavailable_without_data_or_reconstruction() -> None:
    execution_context = _context()
    tool = VisibleCockpitResultTool()

    result = tool.execute(
        "call-stale",
        VisibleCockpitResultArguments(f"sha256:{'0' * 64}"),
        execution_context,
    )

    assert result.status is AgentToolExecutionStatus.UNAVAILABLE
    assert result.data is None
    assert result.error_code == "VISIBLE_RESULT_UNAVAILABLE"


@pytest.mark.parametrize(
    "reference",
    (
        "",
        "sha256:abc",
        f"sha256:{'A' * 64}",
        f"sha512:{'0' * 64}",
        f"sha256:{'0' * 63}",
    ),
)
def test_argument_rejects_noncanonical_reference(reference: str) -> None:
    with pytest.raises(ValueError, match="canonical sha256"):
        VisibleCockpitResultArguments(reference)


def test_tool_constructor_has_no_io_or_provider_dependencies() -> None:
    tool = VisibleCockpitResultTool()

    assert vars(tool) == {}
