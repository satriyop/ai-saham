"""DTOs and serialization contracts for swing analysis workflow output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.plan_swing_serialization import (
    candidate_accumulation_to_dict,
    object_to_dict,
    risk_response_to_dict,
    risk_response_to_preview_dict,
    signal_response_to_dict,
    volatility_context_to_dict,
)
from src.application.services.position_sizer import PercentSizingResult, SizingResult


class SignalAssessmentStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class SignalAssessmentUnavailableReason(str, Enum):
    NO_PRODUCTION_SIGNAL_EVIDENCE = "no_production_signal_evidence"
    SIGNAL_ENGINE_UNAVAILABLE = "signal_engine_unavailable"
    ASSESSMENT_FAILED = "assessment_failed"


@dataclass(frozen=True)
class SignalAssessmentAvailability:
    status: SignalAssessmentStatus
    unavailable_reason: SignalAssessmentUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SignalAssessmentStatus):
            raise TypeError("status must be a SignalAssessmentStatus")
        if self.unavailable_reason is not None and not isinstance(
            self.unavailable_reason, SignalAssessmentUnavailableReason
        ):
            raise TypeError("unavailable_reason must be a SignalAssessmentUnavailableReason")

        if self.status == SignalAssessmentStatus.AVAILABLE:
            if self.unavailable_reason is not None:
                raise ValueError("AVAILABLE requires no unavailable reason.")
        elif self.status == SignalAssessmentStatus.UNAVAILABLE:
            if self.unavailable_reason is None:
                raise ValueError("UNAVAILABLE requires a reason.")


if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.domain.value_objects.company_quality_context_evidence import (
        CompanyQualityContextEvidence,
    )
    from src.domain.value_objects.corporate_action_event_risk import (
        CorporateActionRiskAssessment,
    )
    from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
    from src.domain.value_objects.institutional_accumulation_evidence import (
        InstitutionalAccumulationEvidence,
    )
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.sector_context_evidence import SectorContextEvidence
    from src.domain.value_objects.sector_macro_context_evidence import (
        SectorMacroContextEvidence,
    )
    from src.domain.value_objects.setup_evidence import SetupEvidence
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
    from src.domain.value_objects.strategy_evidence import StrategyEvidence
    from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot
    from src.domain.value_objects.trade_setup import TradeSetup


@dataclass(frozen=True)
class PlanSwingWorkflowRequest:
    ticker: str
    today: date
    strategy_name: str | None
    setup_name: str | None
    window: int
    flow_window: int
    capital: int | None
    risk_pct: float
    entry_price: float | None
    atr_mult: float
    rr: float
    include_sentiment: bool
    include_flow_detail: bool
    include_signal_detail: bool
    include_risk_detail: bool
    include_market_detail: bool
    sentiment_verbose: bool
    auto_refresh: bool
    force_refresh: bool
    with_market_context: bool
    regime_universe: str
    benchmark: str
    db_path: Path
    with_technical_gate: bool = False


@dataclass(frozen=True)
class SwingVerdict:
    """Decision-producing outputs for swing analysis."""

    trade_setup: "TradeSetup | None"
    signal_assessment: "AssessSignalResponse | None"
    risk_response: Any | None
    market_regime: "MarketContext | None"
    signal_assessment_availability: SignalAssessmentAvailability
    market_context_signal_preview: "AssessSignalResponse | None" = None
    market_context_risk_preview: Any | None = None
    market_context_trade_setup_preview: "TradeSetup | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.signal_assessment_availability, SignalAssessmentAvailability):
            raise TypeError("signal_assessment_availability must be a SignalAssessmentAvailability")

        status = self.signal_assessment_availability.status
        if status == SignalAssessmentStatus.AVAILABLE:
            if self.signal_assessment is None:
                raise ValueError("AVAILABLE requires signal_assessment to be present.")
        elif status == SignalAssessmentStatus.UNAVAILABLE:
            if self.signal_assessment is not None:
                raise ValueError("UNAVAILABLE requires signal_assessment to be None.")
            if self.trade_setup is not None:
                raise ValueError("UNAVAILABLE requires trade_setup to be None.")
            if self.market_context_signal_preview is not None:
                raise ValueError("UNAVAILABLE requires market_context_signal_preview to be None.")
            if self.market_context_trade_setup_preview is not None:
                raise ValueError(
                    "UNAVAILABLE requires market_context_trade_setup_preview to be None."
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_setup": self.trade_setup.to_dict() if self.trade_setup else None,
            "signal_assessment": signal_response_to_dict(self.signal_assessment),
            "risk_assessment": risk_response_to_dict(self.risk_response),
            "market_context": (self.market_regime.to_dict() if self.market_regime else None),
            "signal_assessment_status": (
                self.signal_assessment_availability.status.value
                if self.signal_assessment_availability
                else None
            ),
            "signal_assessment_unavailable_reason": (
                self.signal_assessment_availability.unavailable_reason.value
                if self.signal_assessment_availability
                and self.signal_assessment_availability.unavailable_reason
                else None
            ),
            "market_context_preview": (
                {
                    "signal_preview": signal_response_to_dict(self.market_context_signal_preview),
                    "risk_preview": risk_response_to_preview_dict(self.market_context_risk_preview),
                    "trade_setup_preview": (
                        self.market_context_trade_setup_preview.to_dict()
                        if self.market_context_trade_setup_preview
                        else None
                    ),
                }
                if self.market_regime
                else None
            ),
        }


@dataclass(frozen=True)
class SwingEvidence:
    """Supporting evidence that informs or explains swing analysis."""

    accumulation_candidate: Any | None
    setup_eval: Any | None
    backtest_result: Any | None
    sentiment_response: Any | None
    sentiment_warning: str | None
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    regime_label: str | None
    setup_evidence: "SetupEvidence | None" = None
    flow_confirmation_evidence: "FlowConfirmationEvidence | None" = None
    setup_phase: "SetupPhaseSnapshot | None" = None
    strategy_rule_evidence: "StrategyEvidence | None" = None
    institutional_accumulation_evidence: "InstitutionalAccumulationEvidence | None" = None
    ticker_profile_snapshot: "TickerProfileSnapshot | None" = None
    sector_context_evidence: "SectorContextEvidence | None" = None
    sector_macro_context_evidence: "SectorMacroContextEvidence | None" = None
    company_quality_context_evidence: "CompanyQualityContextEvidence | None" = None
    corporate_action_risk: "CorporateActionRiskAssessment | None" = None

    def to_dict(
        self, *, strategy_name: str | None = None, max_hold_days: int | None = None
    ) -> dict[str, Any]:
        candidate = self.accumulation_candidate
        setup_eval = self.setup_eval
        backtest_result = self.backtest_result
        sentiment_resp = self.sentiment_response
        return {
            "foreign_flow_evidence": (
                candidate.foreign_flow_evidence.to_dict()
                if candidate and getattr(candidate, "foreign_flow_evidence", None)
                else None
            ),
            "accumulation": candidate_accumulation_to_dict(candidate),
            "setup": (
                {
                    "name": setup_eval.name if setup_eval else None,
                    "passed": setup_eval.passed if setup_eval else None,
                    "match": setup_eval.match.value if setup_eval else None,
                    "failed_reasons": list(setup_eval.failed_reasons) if setup_eval else [],
                    "plan": {
                        "take_profit_pct": float(self.take_profit_pct) if setup_eval else None,
                        "stop_loss_pct": float(self.stop_loss_pct) if setup_eval else None,
                        "regime": self.regime_label,
                        "max_hold_days": max_hold_days if setup_eval else None,
                    },
                }
                if setup_eval
                else None
            ),
            "strategy_evidence": (
                {
                    "name": strategy_name,
                    "win_rate": float(backtest_result.win_rate) if backtest_result else None,
                    "profit_factor": (
                        float(backtest_result.profit_factor) if backtest_result else None
                    ),
                    "max_drawdown_pct": (
                        float(backtest_result.max_drawdown_pct) if backtest_result else None
                    ),
                    "trade_count": backtest_result.trade_count if backtest_result else None,
                    "diagnostic": (
                        self.strategy_rule_evidence.to_dict()
                        if self.strategy_rule_evidence
                        else None
                    ),
                }
                if strategy_name
                else None
            ),
            "sentiment": {
                "call": (
                    sentiment_resp.snapshot.overall_sentiment.value
                    if sentiment_resp and not sentiment_resp.warning
                    else None
                ),
                "warning": self.sentiment_warning,
                "total_headlines": (
                    sentiment_resp.snapshot.total_count
                    if sentiment_resp and not sentiment_resp.warning
                    else None
                ),
                "confidence_pct": (
                    sentiment_resp.snapshot.confidence_pct
                    if sentiment_resp and not sentiment_resp.warning
                    else None
                ),
            },
            "setup_evidence": self.setup_evidence.to_dict() if self.setup_evidence else None,
            "setup_phase": self.setup_phase.to_dict() if self.setup_phase else None,
            "strategy_rule_evidence": (
                self.strategy_rule_evidence.to_dict() if self.strategy_rule_evidence else None
            ),
            "flow_confirmation_evidence": (
                self.flow_confirmation_evidence.to_dict()
                if self.flow_confirmation_evidence
                else None
            ),
            "institutional_accumulation_evidence": (
                self.institutional_accumulation_evidence.to_dict()
                if self.institutional_accumulation_evidence
                else None
            ),
            "ticker_profile_snapshot": (
                self.ticker_profile_snapshot.to_dict() if self.ticker_profile_snapshot else None
            ),
            "sector_context_evidence": (
                self.sector_context_evidence.to_dict() if self.sector_context_evidence else None
            ),
            "sector_macro_context_evidence": (
                self.sector_macro_context_evidence.to_dict()
                if self.sector_macro_context_evidence
                else None
            ),
            "company_quality_context_evidence": (
                self.company_quality_context_evidence.to_dict()
                if self.company_quality_context_evidence
                else None
            ),
            "corporate_action_risk": (
                self.corporate_action_risk.to_dict() if self.corporate_action_risk else None
            ),
        }


@dataclass(frozen=True)
class SwingDiagnostics:
    """Data quality and diagnostic outputs for swing analysis."""

    data_freshness: Any
    flow_detail: Any
    broker_detail: Any
    broker_quality_note: Any | None
    refresh_actions: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data_out = object_to_dict(self.data_freshness)
        return {
            "data": data_out,
            "flow_detail": object_to_dict(self.flow_detail),
            "broker_detail": object_to_dict(self.broker_detail),
            "broker_quality_note": object_to_dict(self.broker_quality_note),
            "refresh_actions": list(self.refresh_actions),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PlanSwingWorkflowResponse:
    ticker: str
    today: date
    refresh_actions: tuple[str, ...]
    data_freshness: Any
    flow_detail: Any
    broker_detail: Any
    candles: list[Any]
    latest_close: Decimal
    accumulation_candidate: Any | None
    risk_response: Any | None
    atr_value: Decimal | None
    sizing: SizingResult | None
    setup_eval: Any | None
    setup_sizing: PercentSizingResult | None
    broker_quality_note: Any | None
    backtest_result: Any | None
    sentiment_response: Any | None
    sentiment_warning: str | None
    market_regime: "MarketContext | None"
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    regime_label: str | None
    signal_assessment_availability: SignalAssessmentAvailability
    signal_assessment: "AssessSignalResponse | None" = None
    trade_setup: "TradeSetup | None" = None
    market_context_signal_preview: "AssessSignalResponse | None" = None
    market_context_risk_preview: Any | None = None
    market_context_trade_setup_preview: "TradeSetup | None" = None
    verdict: SwingVerdict | None = None
    evidence: SwingEvidence | None = None
    diagnostics: SwingDiagnostics | None = None
    modules: dict[str, bool] | None = None
    warnings: tuple[str, ...] = ()
    effective_session: EffectiveMarketSession | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.signal_assessment_availability, SignalAssessmentAvailability):
            raise TypeError("signal_assessment_availability must be a SignalAssessmentAvailability")

        status = self.signal_assessment_availability.status
        if status == SignalAssessmentStatus.AVAILABLE:
            if self.signal_assessment is None:
                raise ValueError("AVAILABLE requires signal_assessment to be present.")
        elif status == SignalAssessmentStatus.UNAVAILABLE:
            if self.signal_assessment is not None:
                raise ValueError("UNAVAILABLE requires signal_assessment to be None.")

        if self.verdict is not None:
            if self.signal_assessment_availability != self.verdict.signal_assessment_availability:
                raise ValueError("Response availability must match verdict availability.")
            if self.signal_assessment is not self.verdict.signal_assessment:
                raise ValueError("Response signal_assessment must match verdict signal_assessment.")
            if self.trade_setup is not self.verdict.trade_setup:
                raise ValueError("Response trade_setup must match verdict trade_setup.")

    def to_dict(
        self,
        *,
        strategy_name: str | None = None,
        max_hold_days: int | None = None,
        include_sentiment: bool = True,
    ) -> dict[str, Any]:
        verdict = self.verdict or SwingVerdict(
            trade_setup=self.trade_setup,
            signal_assessment=self.signal_assessment,
            risk_response=self.risk_response,
            market_regime=self.market_regime,
            market_context_signal_preview=self.market_context_signal_preview,
            market_context_risk_preview=self.market_context_risk_preview,
            market_context_trade_setup_preview=self.market_context_trade_setup_preview,
            signal_assessment_availability=self.signal_assessment_availability,
        )
        evidence = self.evidence or SwingEvidence(
            accumulation_candidate=self.accumulation_candidate,
            setup_eval=self.setup_eval,
            backtest_result=self.backtest_result,
            sentiment_response=self.sentiment_response,
            sentiment_warning=self.sentiment_warning,
            take_profit_pct=self.take_profit_pct,
            stop_loss_pct=self.stop_loss_pct,
            regime_label=self.regime_label,
        )
        diagnostics = self.diagnostics or SwingDiagnostics(
            data_freshness=self.data_freshness,
            flow_detail=self.flow_detail,
            broker_detail=self.broker_detail,
            broker_quality_note=self.broker_quality_note,
            refresh_actions=self.refresh_actions,
            warnings=self.warnings,
        )
        diagnostics_out = diagnostics.to_dict()
        if isinstance(diagnostics_out.get("data"), dict) and verdict.market_regime is not None:
            diagnostics_out["data"]["regime_as_of"] = verdict.market_regime.as_of_date.isoformat()
        diagnostics_out["volatility_context"] = volatility_context_to_dict(
            atr_value=self.atr_value,
            latest_close=self.latest_close,
        )
        evidence_out = evidence.to_dict(
            strategy_name=strategy_name,
            max_hold_days=max_hold_days,
        )
        if not include_sentiment:
            evidence_out["sentiment"] = None

        return {
            "schema_version": 1,
            "artifact_type": "plan_swing",
            "json_contract": {
                "canonical": ("verdict", "evidence", "diagnostics"),
            },
            "ticker": self.ticker,
            "date": str(self.today),
            "effective_session": (
                self.effective_session.to_dict() if self.effective_session is not None else None
            ),
            "modules": self.modules or {},
            "verdict": verdict.to_dict(),
            "evidence": evidence_out,
            "diagnostics": diagnostics_out,
        }
