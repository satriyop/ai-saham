"""
Application workflow coordinator for `saham screen pre-open`.

Layer: Application
AI usage: Optional, only when caller injects an AI-enabled PreOpenScreenUseCase.

Engine adoption (ADR-047 / ADR-048):
  regime + risk (annotate) always-on via ScreenAssessmentPipeline;
  pre-open v1 signal cascade when auction_ncp evidence is present;
  TradeSetup composed when signal + risk assessments both exist.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.services.pre_open_risk_inputs_builder import PreOpenRiskInputsBuilder
from src.application.services.pre_open_signal_cascade import PreOpenSignalInputsBuilder
from src.application.services.pre_open_signal_config import PreOpenSignalConfig
from src.application.services.screen_assessment_pipeline import ScreenAssessmentPipeline
from src.application.services.screen_policy import ScreenPolicy
from src.application.use_case.assess_risk_use_case import AssessRiskResponse
from src.application.use_case.assess_trade_setup_use_case import (
    AssessTradeSetupUseCase,
)
from src.application.use_case.pre_open_screen_use_case import (
    PreOpenScreenConfig,
    PreOpenScreenRequest,
    PreOpenScreenResponse,
    PreOpenScreenUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.browser_data_provider import (
    BrowserDataProviderError,
    BrowserInteractionRequired,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker
from src.domain.value_objects.idx_market import PRE_OPEN_START
from src.domain.value_objects.idx_market import REGULAR_OPEN as PRE_OPEN_END
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
from src.domain.value_objects.screener_result import (
    PreOpenScreenResult,
    ScreenerCandidate,
)
from src.domain.value_objects.trade_setup import TradeSetup

if TYPE_CHECKING:
    from src.application.services.risk_engine import RiskEngine
    from src.domain.value_objects.market_context import MarketContext


@dataclass(frozen=True)
class PreOpenDataFreshness:
    """Data-source dates used by the pre-open screen."""

    analysis_date: date
    candle_end: date | None
    broker_end: date | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreOpenRiskSummary:
    """Compact per-ticker risk projection for pre-open (not full AssessRiskResponse)."""

    risk_level_name: str
    gate_triggered: str | None = None
    gate_is_structural: bool | None = None
    confidence: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level_name": self.risk_level_name,
            "gate_triggered": self.gate_triggered,
            "gate_is_structural": self.gate_is_structural,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PreOpenWorkflowRequest:
    config: PreOpenScreenConfig
    run_date: date
    guard_warnings: tuple[str, ...] = ()
    # Defaults ON (Tier-1). CLI exposes --no-regime / --no-risk opt-out.
    regime_enabled: bool = True
    risk_enabled: bool = True
    # ADR-048 signal cascade (default on; hard-guards per ticker without auction).
    signal_enabled: bool = True
    regime_universe: str = "idx80"
    benchmark: str = "IHSG"
    db_path: Path = Path("data.db")
    outside_window: bool = False
    # NCP capture metadata for evidence provenance (optional).
    capture_phase: str = "UNKNOWN"
    decision_snapshot_ref: str | None = None


@dataclass(frozen=True)
class PreOpenSnapshotScreenResult:
    """A saved-snapshot screen run, used as the outside-window fallback."""

    snapshot_date: date
    response: PreOpenScreenResponse


@dataclass(frozen=True)
class PreOpenSignalSummary:
    """Compact signal projection for envelope/display (not TradeSetup)."""

    score: int
    strength: str
    entry_quality: str
    signal_authority_coverage: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "strength": self.strength,
            "entry_quality": self.entry_quality,
            "signal_authority_coverage": self.signal_authority_coverage,
        }


@dataclass(frozen=True)
class PreOpenWorkflowResponse:
    result: PreOpenScreenResult
    warnings: list[str]
    raw_movers: list
    data_freshness: PreOpenDataFreshness
    market_regime: "MarketContext | None" = None
    risk_by_ticker: dict[str, PreOpenRiskSummary | None] | None = None
    signal_by_ticker: dict[str, PreOpenSignalSummary | None] | None = None
    trade_setup_by_ticker: dict[str, TradeSetup | None] | None = None
    regime_enabled: bool = True
    risk_enabled: bool = True
    signal_enabled: bool = True
    source_status: PreOpenSourceStatus = PreOpenSourceStatus.LIVE_SUCCESS
    source_message: str | None = None
    source_snapshot_ref: str | None = None


class PreOpenWorkflowUseCase:
    """Run the pre-open screen and attach deterministic workflow context."""

    def __init__(
        self,
        screen_use_case: PreOpenScreenUseCase,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        evaluate_market_context: Callable[..., "MarketContext"] | None = None,
        risk_engine: "RiskEngine | None" = None,
        assessment_pipeline: ScreenAssessmentPipeline | None = None,
        signal_builder: PreOpenSignalInputsBuilder | None = None,
        trade_setup_uc: AssessTradeSetupUseCase | None = None,
        run_snapshot_screen: (
            Callable[[PreOpenScreenConfig, date], PreOpenSnapshotScreenResult | None] | None
        ) = None,
    ) -> None:
        self._screen_use_case = screen_use_case
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._evaluate_market_context = evaluate_market_context
        self._run_snapshot_screen = run_snapshot_screen
        self._assessment_pipeline = assessment_pipeline or ScreenAssessmentPipeline(
            policy=ScreenPolicy.pre_open(),
            risk_engine=risk_engine,
            risk_inputs_builder=PreOpenRiskInputsBuilder() if risk_engine is not None else None,
            evaluate_market_context=evaluate_market_context,
        )
        self._signal_builder = signal_builder or PreOpenSignalInputsBuilder(
            PreOpenSignalConfig()
        )
        self._trade_setup_uc = trade_setup_uc or AssessTradeSetupUseCase()

    def execute(self, request: PreOpenWorkflowRequest) -> PreOpenWorkflowResponse:
        if request.outside_window:
            if self._run_snapshot_screen is not None:
                snapshot = self._run_snapshot_screen(request.config, request.run_date)
                if snapshot is not None:
                    message = f"Snapshot dated {snapshot.snapshot_date.isoformat()} used (outside live window)."
                    return self._finish(
                        request,
                        snapshot.response,
                        source_status=PreOpenSourceStatus.SNAPSHOT_SUCCESS,
                        source_message=message,
                        source_snapshot_ref=snapshot.snapshot_date.isoformat(),
                    )
            return self._outside_window_response(request)

        try:
            screen_response = self._screen_use_case.execute(
                PreOpenScreenRequest(
                    config=request.config,
                    run_date=request.run_date,
                )
            )
        except BrowserInteractionRequired:
            raise
        except BrowserDataProviderError as exc:
            return self._unavailable_response(request, exc)

        if screen_response.result.total_movers_seen == 0:
            source_status = PreOpenSourceStatus.EMPTY_CONFIRMED
            source_message = "Provider returned a valid empty mover list."
        else:
            source_status = PreOpenSourceStatus.LIVE_SUCCESS
            source_message = None

        return self._finish(
            request,
            screen_response,
            source_status=source_status,
            source_message=source_message,
        )

    def _finish(
        self,
        request: PreOpenWorkflowRequest,
        screen_response: PreOpenScreenResponse,
        *,
        source_status: PreOpenSourceStatus,
        source_message: str | None,
        source_snapshot_ref: str | None = None,
    ) -> PreOpenWorkflowResponse:
        result = screen_response.result
        warnings = list(screen_response.warnings) + list(request.guard_warnings)

        data_freshness = self._build_data_freshness(
            candidates=result.candidates,
            analysis_date=result.screened_date,
        )

        market_regime = None
        if request.regime_enabled and self._evaluate_market_context is not None:
            try:
                market_regime = self._assessment_pipeline.evaluate_regime(
                    db_path=request.db_path,
                    as_of_date=result.screened_date,
                    universe=request.regime_universe,
                    benchmark=canonicalize_ticker(request.benchmark),
                )
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")
        # If regime_enabled but evaluator not injected (partial DI / unit tests),
        # leave market_regime=None without warning. Production CLI always wires MCE.

        risk_by_ticker: dict[str, PreOpenRiskSummary | None] | None = None
        risk_responses: dict[str, AssessRiskResponse] = {}
        if request.risk_enabled:
            has_risk_path = self._assessment_pipeline._risk_inputs_builder is not None and (
                self._assessment_pipeline._risk_engine is not None
                or self._assessment_pipeline._risk_use_case is not None
            )
            if has_risk_path:
                risk_by_ticker, risk_responses, risk_warnings = self._build_risk_summaries(
                    candidates=result.candidates,
                    as_of_date=result.screened_date,
                    market_context=market_regime,
                )
                warnings.extend(risk_warnings)
            # else: composition root did not wire risk (partial DI / unit tests).
            # Production CLI factory always injects RiskEngine — no warning spam.

        signal_by_ticker: dict[str, PreOpenSignalSummary | None] | None = None
        signal_responses: dict[str, AssessSignalResponse] = {}
        trade_setup_by_ticker: dict[str, TradeSetup | None] | None = None
        policy = self._assessment_pipeline.policy

        if (
            request.signal_enabled
            and policy.signal_applicable
            and result.candidates
        ):
            signal_by_ticker = {}
            capture_phase = request.capture_phase
            if source_status is PreOpenSourceStatus.SNAPSHOT_SUCCESS:
                capture_phase = "NCP_LOCKED"
            for candidate in result.candidates:
                try:
                    sig = self._signal_builder.evaluate(
                        candidate,
                        trade_date=result.screened_date,
                        capture_phase=capture_phase,
                        snapshot_ref=request.decision_snapshot_ref
                        or source_snapshot_ref,
                    )
                except Exception as exc:
                    warnings.append(
                        f"Signal unavailable for {candidate.ticker}: {exc}"
                    )
                    signal_by_ticker[candidate.ticker] = None
                    continue
                if sig is None:
                    signal_by_ticker[candidate.ticker] = None
                    continue
                signal_responses[candidate.ticker] = sig
                signal_by_ticker[candidate.ticker] = PreOpenSignalSummary(
                    score=sig.score,
                    strength=sig.assessment.strength.value,
                    entry_quality=sig.assessment.entry_quality.value,
                    signal_authority_coverage=sig.signal_authority_coverage,
                )

            if policy.trade_setup_applicable and signal_responses:
                trade_setup_by_ticker = {}
                for ticker, sig in signal_responses.items():
                    risk_resp = risk_responses.get(ticker)
                    if risk_resp is None:
                        trade_setup_by_ticker[ticker] = None
                        continue
                    try:
                        setup = self._assessment_pipeline.compose_trade_setup(
                            ticker=ticker,
                            as_of_date=result.screened_date,
                            signal_response=sig,
                            risk_response=risk_resp,
                            market_context=market_regime,
                        )
                        trade_setup_by_ticker[ticker] = setup
                    except Exception as exc:
                        warnings.append(f"TradeSetup unavailable for {ticker}: {exc}")
                        trade_setup_by_ticker[ticker] = None
                # Ensure keys for signal-null tickers absent from trade map
                for ticker in signal_by_ticker:
                    trade_setup_by_ticker.setdefault(ticker, None)

        return PreOpenWorkflowResponse(
            result=result,
            warnings=warnings,
            raw_movers=screen_response.raw_movers,
            data_freshness=data_freshness,
            market_regime=market_regime,
            risk_by_ticker=risk_by_ticker,
            signal_by_ticker=signal_by_ticker,
            trade_setup_by_ticker=trade_setup_by_ticker,
            regime_enabled=request.regime_enabled,
            risk_enabled=request.risk_enabled,
            signal_enabled=request.signal_enabled,
            source_status=source_status,
            source_message=source_message,
            source_snapshot_ref=source_snapshot_ref,
        )

    def _build_risk_summaries(
        self,
        candidates: list[ScreenerCandidate],
        as_of_date: date,
        market_context: "MarketContext | None",
    ) -> tuple[
        dict[str, PreOpenRiskSummary | None],
        dict[str, AssessRiskResponse],
        list[str],
    ]:
        """Assess default-gate risk via pipeline; project compact summaries.

        Soft per-ticker failures → None entry + aggregate warning. Never drops
        candidates (annotate policy). Returns full responses for TradeSetup.
        """
        summaries: dict[str, PreOpenRiskSummary | None] = {}
        full: dict[str, AssessRiskResponse] = {}
        failures = 0
        sample_error: str | None = None

        for candidate in candidates:
            try:
                resp = self._assessment_pipeline.assess_risk(
                    candidate,
                    as_of_date=as_of_date,
                    market_context=market_context,
                )
                if resp is None:
                    summaries[candidate.ticker] = None
                    failures += 1
                    continue
                full[candidate.ticker] = resp
                assessment = resp.assessment
                summaries[candidate.ticker] = PreOpenRiskSummary(
                    risk_level_name=assessment.risk_level_name,
                    gate_triggered=assessment.gate_triggered,
                    gate_is_structural=assessment.gate_is_structural,
                    confidence=assessment.gate_confidence,
                )
            except Exception as exc:
                summaries[candidate.ticker] = None
                failures += 1
                if sample_error is None:
                    sample_error = str(exc)

        warn_list: list[str] = []
        if failures:
            total = len(candidates)
            msg = f"Risk unavailable for {failures}/{total} candidates"
            if sample_error:
                msg = f"{msg} (e.g. {sample_error})"
            warn_list.append(msg)
        return summaries, full, warn_list

    def _outside_window_response(
        self, request: PreOpenWorkflowRequest
    ) -> PreOpenWorkflowResponse:
        message = (
            "Outside the pre-open live window "
            f"({PRE_OPEN_START.strftime('%H:%M')}-{PRE_OPEN_END.strftime('%H:%M')} WIB); "
            "no snapshot fallback available."
        )
        return PreOpenWorkflowResponse(
            result=self._empty_result(request),
            warnings=list(request.guard_warnings),
            raw_movers=[],
            data_freshness=self._empty_data_freshness(request.run_date),
            regime_enabled=request.regime_enabled,
            risk_enabled=request.risk_enabled,
            source_status=PreOpenSourceStatus.OUTSIDE_WINDOW,
            source_message=message,
        )

    def _unavailable_response(
        self, request: PreOpenWorkflowRequest, exc: Exception
    ) -> PreOpenWorkflowResponse:
        return PreOpenWorkflowResponse(
            result=self._empty_result(request),
            warnings=list(request.guard_warnings),
            raw_movers=[],
            data_freshness=self._empty_data_freshness(request.run_date),
            regime_enabled=request.regime_enabled,
            risk_enabled=request.risk_enabled,
            source_status=PreOpenSourceStatus.UNAVAILABLE,
            source_message=str(exc),
        )

    @staticmethod
    def _empty_result(request: PreOpenWorkflowRequest) -> PreOpenScreenResult:
        return PreOpenScreenResult(
            screened_date=request.run_date,
            iev_min=request.config.iev_min,
            total_movers_seen=0,
            candidates=[],
        )

    @staticmethod
    def _empty_data_freshness(analysis_date: date) -> PreOpenDataFreshness:
        return PreOpenDataFreshness(
            analysis_date=analysis_date,
            candle_end=None,
            broker_end=None,
        )

    def _build_data_freshness(
        self,
        candidates: list[ScreenerCandidate],
        analysis_date: date,
    ) -> PreOpenDataFreshness:
        tickers = sorted({candidate.ticker.upper() for candidate in candidates})
        candle_dates: list[date] = []
        broker_dates: list[date] = []

        for ticker in tickers:
            candle_range = self._market_repo.get_date_range(ticker)
            if candle_range:
                candle_dates.append(candle_range[1])
            broker_range = self._broker_repo.get_date_range(ticker)
            if broker_range:
                broker_dates.append(broker_range[1])

        candle_end = _min_latest_date(candle_dates)
        broker_end = _min_latest_date(broker_dates)
        warnings: list[str] = []

        if candle_end is None:
            warnings.append("No cached candle date found for screened candidates.")
        elif candle_end < analysis_date:
            lag = (analysis_date - candle_end).days
            warnings.append(
                f"Latest candle date is {candle_end}, "
                f"{lag} calendar day(s) before analysis date."
            )

        if broker_end is None:
            warnings.append("No cached broker-flow date found for screened candidates.")
        elif broker_end < analysis_date:
            lag = (analysis_date - broker_end).days
            warnings.append(
                f"Latest broker-flow date is {broker_end}, "
                f"{lag} calendar day(s) before analysis date."
            )

        if candle_end and broker_end and candle_end != broker_end:
            warnings.append(
                f"Candle and broker-flow dates differ ({candle_end} vs {broker_end})."
            )

        return PreOpenDataFreshness(
            analysis_date=analysis_date,
            candle_end=candle_end,
            broker_end=broker_end,
            warnings=tuple(warnings),
        )


def _min_latest_date(dates: list[date]) -> date | None:
    if not dates:
        return None
    return min(dates)
