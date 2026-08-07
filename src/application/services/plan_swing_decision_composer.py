"""Screen-judgment reference phase for the plan swing structure workflow.

Layer: Application. This collaborator does not own or invoke any decision
engine. It carries the one embedded screen result into the plan response.
"""

from __future__ import annotations

from src.application.dto import plan_swing as plan_swing_dto
from src.application.services.plan_swing_workflow_state import PlanSwingWorkflowState
from src.application.services.swing_judgment_authority import resolve_screen_judgment


class PlanSwingDecisionComposer:
    """Resolve the exact screen-owned judgment for structure consumers."""

    def resolve_screen_judgment(
        self,
        request: plan_swing_dto.PlanSwingWorkflowRequest,
        state: PlanSwingWorkflowState,
    ) -> PlanSwingWorkflowState:
        judgment_ref = resolve_screen_judgment(
            state.accumulation_evaluation,
            expected_ticker=request.ticker,
            expected_snapshot_date=request.today,
        )
        candidate = state.accumulation_candidate
        state.judgment_ref = judgment_ref
        state.verdict = plan_swing_dto.SwingVerdict(
            judgment_ref=judgment_ref,
            signal_assessment=(candidate.signal_assessment if candidate is not None else None),
            risk_assessment=(candidate.risk_assessment if candidate is not None else None),
        )
        return state
