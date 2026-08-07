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
    signal_response_to_dict,
    volatility_context_to_dict,
)
from src.application.services.position_sizer import PercentSizingResult, SizingResult


class ScreenJudgmentStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ScreenJudgmentSource(str, Enum):
    SCREEN_ACCUM = "screen_accum"


class ScreenJudgmentUnavailableReason(str, Enum):
    NO_SCREEN_CANDIDATE = "no_screen_candidate"
    NO_SCREEN_SIGNAL_ASSESSMENT = "no_screen_signal_assessment"
    NO_SCREEN_RISK_ASSESSMENT = "no_screen_risk_assessment"
    NO_SCREEN_TRADE_SETUP = "no_screen_trade_setup"


@dataclass(frozen=True)
class ScreenJudgmentReference:
    """Exact screen-owned judgment consumed by the structure workflow."""

    status: ScreenJudgmentStatus
    source: ScreenJudgmentSource
    ticker: str
    snapshot_date: date
    trade_setup: "TradeSetup | None"
    unavailable_reason: ScreenJudgmentUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ScreenJudgmentStatus):
            raise TypeError("status must be a ScreenJudgmentStatus")
        if not isinstance(self.source, ScreenJudgmentSource):
            raise TypeError("source must be a ScreenJudgmentSource")
        if self.source != ScreenJudgmentSource.SCREEN_ACCUM:
            raise ValueError("plan judgment source must be screen_accum")
        if not self.ticker or self.ticker != self.ticker.upper():
            raise ValueError("ticker must be a non-empty canonical uppercase ticker")
        if not isinstance(self.snapshot_date, date):
            raise TypeError("snapshot_date must be a date")
        if self.unavailable_reason is not None and not isinstance(
            self.unavailable_reason, ScreenJudgmentUnavailableReason
        ):
            raise TypeError("unavailable_reason must be a ScreenJudgmentUnavailableReason")

        if self.status == ScreenJudgmentStatus.AVAILABLE:
            if self.trade_setup is None:
                raise ValueError("AVAILABLE requires the screen trade_setup")
            if self.unavailable_reason is not None:
                raise ValueError("AVAILABLE requires no unavailable reason.")
            if self.trade_setup.ticker != self.ticker:
                raise ValueError("screen trade_setup ticker does not match judgment reference")
            if self.trade_setup.snapshot_date != self.snapshot_date:
                raise ValueError("screen trade_setup date does not match judgment reference")
        elif self.status == ScreenJudgmentStatus.UNAVAILABLE:
            if self.trade_setup is not None:
                raise ValueError("UNAVAILABLE requires trade_setup to be None")
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
    sentiment_verbose: bool
    auto_refresh: bool
    force_refresh: bool
    db_path: Path


@dataclass(frozen=True)
class SwingVerdict:
    """Referenced screen judgment shown beside plan-owned structure."""

    judgment_ref: ScreenJudgmentReference
    signal_assessment: "AssessSignalResponse | None"
    risk_assessment: Any | None

    def __post_init__(self) -> None:
        if not isinstance(self.judgment_ref, ScreenJudgmentReference):
            raise TypeError("judgment_ref must be a ScreenJudgmentReference")
        if self.judgment_ref.status == ScreenJudgmentStatus.AVAILABLE:
            if self.signal_assessment is None or self.risk_assessment is None:
                raise ValueError("AVAILABLE screen judgment requires screen signal and risk")

    @property
    def trade_setup(self) -> "TradeSetup | None":
        return self.judgment_ref.trade_setup

    def to_dict(self) -> dict[str, Any]:
        trade_setup = self.judgment_ref.trade_setup
        return {
            "status": self.judgment_ref.status.value,
            "source": self.judgment_ref.source.value,
            "ticker": self.judgment_ref.ticker,
            "snapshot_date": self.judgment_ref.snapshot_date.isoformat(),
            "action": trade_setup.action.value if trade_setup is not None else None,
            "trade_setup": trade_setup.to_dict() if trade_setup is not None else None,
            "unavailable_reason": (
                self.judgment_ref.unavailable_reason.value
                if self.judgment_ref.unavailable_reason is not None
                else None
            ),
            "signal_assessment": signal_response_to_dict(self.signal_assessment),
            "risk_assessment": object_to_dict(self.risk_assessment),
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
    atr_value: Decimal | None
    sizing: SizingResult | None
    setup_eval: Any | None
    setup_sizing: PercentSizingResult | None
    broker_quality_note: Any | None
    backtest_result: Any | None
    sentiment_response: Any | None
    sentiment_warning: str | None
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    regime_label: str | None
    judgment_ref: ScreenJudgmentReference
    verdict: SwingVerdict
    evidence: SwingEvidence | None = None
    diagnostics: SwingDiagnostics | None = None
    modules: dict[str, bool] | None = None
    warnings: tuple[str, ...] = ()
    effective_session: EffectiveMarketSession | None = None

    def __post_init__(self) -> None:
        if self.judgment_ref is not self.verdict.judgment_ref:
            raise ValueError("response and verdict must share the exact judgment reference")

    @property
    def trade_setup(self) -> "TradeSetup | None":
        return self.judgment_ref.trade_setup

    @property
    def signal_assessment(self) -> "AssessSignalResponse | None":
        return self.verdict.signal_assessment

    @property
    def screen_risk_assessment(self) -> Any | None:
        return self.verdict.risk_assessment

    def to_dict(
        self,
        *,
        strategy_name: str | None = None,
        max_hold_days: int | None = None,
        include_sentiment: bool = True,
    ) -> dict[str, Any]:
        verdict = self.verdict
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
            "schema_version": 2,
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
