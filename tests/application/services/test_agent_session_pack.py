from datetime import date

import pytest

from src.application.dto.agent_session import (
    AgentReferenceCompatibility,
    AgentSessionPolicy,
    AgentSessionState,
    AgentSessionToolRecord,
)
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_session_pack import (
    build_session_pack,
    classify_context_reference,
    classify_tool_record,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent


def test_same_context_reference_is_fresh() -> None:
    assert (
        classify_context_reference(
            "abc",
            current_context_reference="abc",
            record_ticker="BBCA",
            current_ticker="BBCA",
            record_schema_id="tui_agent.accum_judge.v1",
            current_schema_id="tui_agent.accum_judge.v1",
        )
        is AgentReferenceCompatibility.FRESH
    )


def test_different_ticker_is_incompatible() -> None:
    assert (
        classify_context_reference(
            "abc",
            current_context_reference="abc",
            record_ticker="TLKM",
            current_ticker="BBCA",
            record_schema_id="tui_agent.accum_judge.v1",
            current_schema_id="tui_agent.accum_judge.v1",
        )
        is AgentReferenceCompatibility.INCOMPATIBLE
    )


def test_pack_marks_stale_tools_and_preserves_structural_anchors() -> None:
    current = build_agent_accumulation_context(make_candidate())
    state = AgentSessionState(
        session_id="sess_test",
        turn_count=1,
        anchor_context_reference="old-ref",
        anchor_ticker="BBCA",
        anchor_schema_id=current.schema_id,
        commentary_turns=(),
        older_commentary_summary="",
        tool_records=(
            AgentSessionToolRecord(
                name="get_ticker_dashboard",
                status="SUCCESS",
                result_reference="sha256:tool",
                source_reference="ticker-dashboard:BBCA",
                as_of=date(2026, 8, 1),
                schema_id="agent_tool.ticker_dashboard.result.v1",
                subject="BBCA",
                context_reference="old-ref",
            ),
        ),
        structural_warnings=("prior warning",),
        structural_failures=(),
    )
    pack = build_session_pack(
        state,
        current=current,
        policy=AgentSessionPolicy(enabled=True),
    )
    assert pack.fresh_tool_records == ()
    assert len(pack.stale_or_incompatible_tool_records) == 1
    assert pack.stale_or_incompatible_tool_records[0].compatibility is (
        AgentReferenceCompatibility.STALE
    )
    assert "prior warning" in pack.structural_warnings
    assert any("not current facts" in item for item in pack.pack_warnings)


def test_tool_record_fresh_when_same_context() -> None:
    current = build_agent_accumulation_context(make_candidate())
    record = AgentSessionToolRecord(
        name="get_visible_cockpit_result",
        status="SUCCESS",
        result_reference="sha256:x",
        source_reference=None,
        as_of=None,
        schema_id=None,
        subject="BBCA",
        context_reference=current.context_reference,
    )
    assert classify_tool_record(record, current=current) is AgentReferenceCompatibility.FRESH
