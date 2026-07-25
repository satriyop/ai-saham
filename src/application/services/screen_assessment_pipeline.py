"""ScreenAssessmentPipeline — shared engine adoption for screen scenarios.

Layer: Application

Owns orchestration order and hard guards; scenarios supply SignalInputs /
RiskInputsBuilder / ScreenPolicy. Named Assessment (not Enrichment): this
consumes enrichment and produces assessments (ADR-047).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Callable

from src.application.services.risk_inputs import RiskInputsBuilder
from src.application.services.screen_policy import RiskMode, ScreenPolicy
from src.application.services.signal_inputs import SignalInputs
from src.application.use_case.assess_risk_use_case import AssessRiskRequest
from src.application.use_case.assess_trade_setup_use_case import (
    AssessTradeSetupRequest,
    AssessTradeSetupUseCase,
)

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.signal_engine import SignalEngine
    from src.application.use_case.assess_risk_use_case import (
        AssessRiskResponse,
        AssessRiskUseCase,
    )
    from src.domain.value_objects.market_context import MarketContext

logger = logging.getLogger(__name__)


class ScreenAssessmentPipeline:
    """Orchestrate regime → signal → risk → trade_setup for screen scenarios."""

    def __init__(
        self,
        *,
        policy: ScreenPolicy,
        signal_engine: "SignalEngine | None" = None,
        risk_use_case: "AssessRiskUseCase | None" = None,
        risk_engine: "RiskEngine | None" = None,
        risk_inputs_builder: RiskInputsBuilder | None = None,
        trade_setup_uc: AssessTradeSetupUseCase | None = None,
        evaluate_market_context: Callable[..., Any] | None = None,
    ) -> None:
        self._policy = policy
        self._signal_engine = signal_engine
        self._risk_use_case = risk_use_case
        self._risk_engine = risk_engine
        self._risk_inputs_builder = risk_inputs_builder
        self._trade_setup_uc = trade_setup_uc or AssessTradeSetupUseCase()
        self._evaluate_market_context = evaluate_market_context

    @property
    def policy(self) -> ScreenPolicy:
        return self._policy

    def evaluate_regime(self, **kwargs: Any) -> Any:
        """Run MCE once per screen when a regime evaluator is wired.

        Returns None when no evaluator is configured. Callers that soft-fail
        on data absence should catch exceptions at the workflow boundary.
        """
        if self._evaluate_market_context is None:
            return None
        return self._evaluate_market_context(**kwargs)

    def evaluate_signal(
        self,
        *,
        ticker: str,
        inputs: SignalInputs,
        market_context: "MarketContext | None" = None,
    ) -> "AssessSignalResponse | None":
        """Evaluate signal with hard guards. Never fabricates evidence.

        Skips (returns None, does not call the engine) when:
        - ``signal_applicable`` is False, or
        - ``canonical_evidence`` is None.
        """
        if not self._policy.signal_applicable:
            return None
        if inputs.canonical_evidence is None:
            return None
        if self._signal_engine is None:
            raise RuntimeError(
                "ScreenAssessmentPipeline: signal_engine is required when "
                "signal_applicable is True"
            )
        return self._signal_engine.evaluate_with_context(
            ticker,
            inputs.signal_context,
            market_context=market_context,
            canonical_evidence=inputs.canonical_evidence,
            setup_family=inputs.setup_family,
            setup_phase=inputs.setup_phase,
            authority_denominator_scope=inputs.authority_denominator_scope,
        )

    def assess_risk(
        self,
        candidate: object,
        *,
        as_of_date: date,
        market_context: "MarketContext | None" = None,
    ) -> "AssessRiskResponse | None":
        """Assess risk using the scenario RiskInputsBuilder.

        GateContext from builder => pre-built path (AssessRiskUseCase).
        None from builder => self-fetch (RiskEngine.assess).
        """
        if self._risk_inputs_builder is None:
            return None

        gate_ctx = self._risk_inputs_builder.build(candidate, as_of_date=as_of_date)
        ticker = getattr(candidate, "ticker", None)
        if not isinstance(ticker, str) or not ticker:
            raise TypeError("candidate must expose a string ticker for risk assessment")

        if gate_ctx is not None:
            if self._risk_use_case is None:
                raise RuntimeError(
                    "ScreenAssessmentPipeline: risk_use_case is required for "
                    "pre-built GateContext path"
                )
            return self._risk_use_case.execute(
                AssessRiskRequest(ticker=ticker, gate_context=gate_ctx)
            )

        if self._risk_engine is None:
            raise RuntimeError(
                "ScreenAssessmentPipeline: risk_engine is required for self-fetch path"
            )
        return self._risk_engine.assess(
            ticker, as_of_date=as_of_date, market_context=market_context
        )

    def compose_trade_setup(
        self,
        *,
        ticker: str,
        as_of_date: date,
        signal_response: "AssessSignalResponse",
        risk_response: "AssessRiskResponse",
        market_context: "MarketContext | None" = None,
    ) -> Any | None:
        """Compose TradeSetup when policy allows and signal is present."""
        if not self._policy.trade_setup_applicable:
            return None
        resp = self._trade_setup_uc.execute(
            AssessTradeSetupRequest(
                ticker=ticker,
                snapshot_date=as_of_date,
                signal_response=signal_response,
                risk_response=risk_response,
                market_context=market_context,
            )
        )
        return resp.setup

    def attach_risk_and_trade_setup(
        self,
        candidates: list[Any],
        as_of_date: date,
        *,
        market_context: "MarketContext | None" = None,
    ) -> None:
        """Attach risk (and trade setup when applicable) in-place on candidates.

        Annotate mode: never removes candidates.
        Block mode: still does not drop list members; blocking surfaces via
        TradeSetup action (accum parity). Soft-fails per ticker.
        """
        if self._risk_inputs_builder is None:
            return
        if self._risk_use_case is None and self._risk_engine is None:
            return

        for candidate in candidates:
            try:
                resp = self.assess_risk(
                    candidate, as_of_date=as_of_date, market_context=market_context
                )
                if resp is None:
                    continue
                if hasattr(candidate, "risk_assessment"):
                    candidate.risk_assessment = resp.assessment
                if hasattr(candidate, "risk_gate_evaluations"):
                    candidate.risk_gate_evaluations = resp.gate_evaluations
                if hasattr(candidate, "risk_gate_context_completeness"):
                    candidate.risk_gate_context_completeness = (
                        resp.gate_context_completeness
                    )

                if (
                    self._policy.trade_setup_applicable
                    and self._policy.risk_mode == RiskMode.BLOCK
                    and getattr(candidate, "signal_assessment", None) is not None
                ):
                    try:
                        setup = self.compose_trade_setup(
                            ticker=candidate.ticker,
                            as_of_date=as_of_date,
                            signal_response=candidate.signal_assessment,
                            risk_response=resp,
                            market_context=market_context,
                        )
                        if setup is not None and hasattr(candidate, "trade_setup"):
                            candidate.trade_setup = setup
                    except Exception as exc2:
                        logger.debug(
                            "ScreenAssessmentPipeline: trade_setup failed for %s: %s",
                            getattr(candidate, "ticker", "?"),
                            exc2,
                        )
            except Exception as exc:
                logger.debug(
                    "ScreenAssessmentPipeline: risk failed for %s: %s",
                    getattr(candidate, "ticker", "?"),
                    exc,
                )
