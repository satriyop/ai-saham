"""PlanSwingResponseAssembler preserves one exact judgment reference."""

from datetime import date
from decimal import Decimal

import pytest

from src.application.dto.plan_swing import (
    ScreenJudgmentReference,
    ScreenJudgmentSource,
    ScreenJudgmentStatus,
    ScreenJudgmentUnavailableReason,
    SwingVerdict,
)
from src.application.services.plan_swing_response_assembler import PlanSwingResponseAssembler
from src.application.services.plan_swing_workflow_state import PlanSwingWorkflowState
from tests.application.use_case.plan_swing_workflow_fixtures import _request


def _reference() -> ScreenJudgmentReference:
    return ScreenJudgmentReference(
        status=ScreenJudgmentStatus.UNAVAILABLE,
        source=ScreenJudgmentSource.SCREEN_ACCUM,
        ticker="BBCA",
        snapshot_date=date(2026, 6, 18),
        trade_setup=None,
        unavailable_reason=ScreenJudgmentUnavailableReason.NO_SCREEN_CANDIDATE,
    )


def test_assemble_rejects_state_and_verdict_reference_mismatch() -> None:
    state_ref = _reference()
    verdict_ref = _reference()
    state = PlanSwingWorkflowState(
        judgment_ref=state_ref,
        verdict=SwingVerdict(
            judgment_ref=verdict_ref,
            signal_assessment=None,
            risk_assessment=None,
        ),
        latest_close=Decimal("100"),
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
    )
    with pytest.raises(ValueError, match="share the exact judgment reference"):
        PlanSwingResponseAssembler().assemble(_request(), state)
