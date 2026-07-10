"""Risk and trade-setup composition for accumulation screen survivors."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.use_case.assess_risk_use_case import AssessRiskRequest
from src.application.use_case.assess_trade_setup_use_case import (
    AssessTradeSetupRequest,
    AssessTradeSetupUseCase,
)
from src.domain.rules.risk_gate import GateContext

if TYPE_CHECKING:
    from src.application.use_case.assess_risk_use_case import AssessRiskUseCase

logger = logging.getLogger(__name__)


class AccumulationRiskFunnel:
    """Attach risk assessment and composed trade setup to screened candidates."""

    def __init__(self, risk_use_case: "AssessRiskUseCase") -> None:
        self._risk_use_case = risk_use_case
        self._trade_setup_uc = AssessTradeSetupUseCase()

    def run(
        self,
        candidates: list[accumulation_dto.AccumulationCandidate],
        as_of_date: date,
    ) -> None:
        """Run AssessRiskUseCase on each survivor and attach the result in-place.

        Builds GateContext from already-loaded candidate data — no duplicate
        provider calls (Rec 15: share data snapshots).
        """
        for candidate in candidates:
            try:
                gate_ctx = GateContext(
                    ticker=candidate.ticker,
                    snapshot_date=as_of_date,
                    piotroski_f_score=(
                        candidate.fundamentals.piotroski_f_score if candidate.fundamentals else None
                    ),
                    market_cap_idr=(
                        candidate.fundamentals.market_cap_idr if candidate.fundamentals else None
                    ),
                    free_float_pct=(
                        candidate.shareholding.free_float_pct
                        if candidate.shareholding is not None
                        else None
                    ),
                    five_day_accdist=(
                        candidate.bandar_detector.five_day_accdist
                        if candidate.bandar_detector
                        else None
                    ),
                )
                resp = self._risk_use_case.execute(
                    AssessRiskRequest(
                        ticker=candidate.ticker,
                        gate_context=gate_ctx,
                    )
                )
                candidate.risk_assessment = resp.assessment
                if candidate.signal_assessment is not None:
                    try:
                        trade_resp = self._trade_setup_uc.execute(
                            AssessTradeSetupRequest(
                                ticker=candidate.ticker,
                                snapshot_date=as_of_date,
                                signal_response=candidate.signal_assessment,
                                risk_response=resp,
                            )
                        )
                        candidate.trade_setup = trade_resp.setup
                    except Exception as exc2:
                        logger.debug(
                            "Risk funnel: trade_setup failed for %s: %s", candidate.ticker, exc2
                        )
            except Exception as exc:
                logger.debug("Risk funnel: assessment failed for %s: %s", candidate.ticker, exc)
