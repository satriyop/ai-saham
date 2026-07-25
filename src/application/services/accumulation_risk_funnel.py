"""Accum risk+trade-setup adoption via ScreenAssessmentPipeline.

Seam implementation for accumulation (ADR-047). No parallel risk path.

Layer: Application
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.services.accum_risk_inputs_builder import AccumRiskInputsBuilder
from src.application.services.screen_assessment_pipeline import ScreenAssessmentPipeline
from src.application.services.screen_policy import ScreenPolicy

if TYPE_CHECKING:
    from src.application.use_case.assess_risk_use_case import AssessRiskUseCase


class AccumulationRiskFunnel:
    """Attach risk assessment and composed trade setup to screened candidates.

    Thin accum seam adapter: builds a ScreenAssessmentPipeline with accum
    policy + AccumRiskInputsBuilder and delegates entirely to it.
    """

    def __init__(
        self,
        risk_use_case: "AssessRiskUseCase",
        *,
        pipeline: ScreenAssessmentPipeline | None = None,
    ) -> None:
        self._pipeline = pipeline or ScreenAssessmentPipeline(
            policy=ScreenPolicy.accumulation(),
            risk_use_case=risk_use_case,
            risk_inputs_builder=AccumRiskInputsBuilder(),
        )

    def run(
        self,
        candidates: list[accumulation_dto.AccumulationCandidate],
        as_of_date: date,
    ) -> None:
        """Run risk + trade_setup through the shared pipeline (in-place)."""
        self._pipeline.attach_risk_and_trade_setup(candidates, as_of_date)
