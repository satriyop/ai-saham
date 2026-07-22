"""
Workflow orchestration for saham screen accum command.

Owns multi-window orchestration, min-streak post-filter, tracked-broker-flow
computation, strategy-signal overlay, and watchlist save.  The CLI adapter
calls this single use case and renders the result.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field

from datetime import datetime
from typing import TYPE_CHECKING

from src.application.dto.accumulation_screen import AccumulationScreenResponse

if TYPE_CHECKING:
    from src.application.dto.signal_evidence_execution_context import (
        SignalEvidenceExecutionContext,
    )
    from src.application.use_case.build_live_signal_evidence_execution_context_use_case import (
        BuildLiveSignalEvidenceExecutionContextUseCase,
    )
from src.application.services.tracked_broker_flow import (
    TrackedBrokerFlowSnapshot,
    compute_tracked_broker_flow_batch,
)
from src.application.services.screen_accum_result_projector import (
    ScreenAccumMultiProjection,
    ScreenAccumSingleProjection,
    project_multi_screen_result,
    project_single_screen_result,
    validate_multi_window_request,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from src.application.use_case.save_screen_watchlist_use_case import (
    SaveScreenWatchlistRequest,
    SaveScreenWatchlistResult,
)


@dataclass(frozen=True)
class RunAccumulationScreenWorkflowRequest:
    tickers: list[str]
    universe_label: str
    universe_name: str | None
    window: int
    min_streak: int
    min_foreign_flow_score: float | None
    min_signal_score: float | None
    min_piotroski: int
    strategy_name: str | None
    include_strategy_overlay: bool
    multi: bool
    windows: list[int]
    top: int
    save_name: str | None
    save_enabled: bool
    vwap_only: bool = False
    squeeze_only: bool = False
    sort_by: str = "vwap"


@dataclass(frozen=True)
class RunAccumulationScreenWorkflowResult:
    response: AccumulationScreenResponse | None = None
    single_projection: ScreenAccumSingleProjection | None = None
    multi_results: dict[int, AccumulationScreenResponse] = field(default_factory=dict)
    multi_projection: ScreenAccumMultiProjection | None = None
    tracked_broker_flow: dict[str, TrackedBrokerFlowSnapshot] = field(default_factory=dict)
    strategy_signals: dict[str, str] = field(default_factory=dict)
    save_result: SaveScreenWatchlistResult | None = None
    warnings: tuple[str, ...] = ()


# Baseline broker-data-availability floor for the raw screen request. This is
# deliberately independent of the CLI --min-streak filter: min_streak governs
# consecutive_streak filtering, which is owned exclusively by
# project_single_screen_result() (S2). Coupling this to min_streak would let
# the raw screen silently drop candidates before the projector ever sees
# them, defeating "filters applied exactly once, in the projector."
_BASELINE_MIN_NET_BUY_DAYS = 1

# S7: canonical window whose Signal/Risk/Phase/Data/Next own the --multi
# shortlist evidence. Other requested windows remain flow-only context.
_DEFAULT_MULTI_CANONICAL_WINDOW = 7


class RunAccumulationScreenWorkflowUseCase:
    def __init__(
        self,
        *,
        screen_use_case,
        broker_repository,
        market_repository,
        swing_config,
        accumulation_screener_config,
        rules_loader,
        indicator_registry_factory,
        live_signal_evidence_context_use_case: BuildLiveSignalEvidenceExecutionContextUseCase,
        save_watchlist_use_case=None,
    ) -> None:
        self._screen_use_case = screen_use_case
        self._broker_repository = broker_repository
        self._market_repository = market_repository
        self._swing_config = swing_config
        self._accumulation_screener_config = accumulation_screener_config
        self._rules_loader = rules_loader
        self._indicator_registry_factory = indicator_registry_factory
        self._live_signal_evidence_context_uc = live_signal_evidence_context_use_case
        self._save_watchlist_use_case = save_watchlist_use_case
        # Every mode here (single-window and --multi) is diagnostic/read-only.
        # Canonical observation recording is a separate, explicit workflow
        # (signal-backfill) — see RecordAccumulationObservationsUseCase.

    def execute(
        self,
        request: RunAccumulationScreenWorkflowRequest,
    ) -> RunAccumulationScreenWorkflowResult:
        warnings: list[str] = []

        request_builder = BuildSignalObservationScreenRequest.from_configs(
            swing_config=self._swing_config,
            accumulation_screener_config=self._accumulation_screener_config,
            min_net_buy_days=_BASELINE_MIN_NET_BUY_DAYS,
            min_foreign_flow_score=request.min_foreign_flow_score,
            min_signal_score=request.min_signal_score,
            min_piotroski=request.min_piotroski,
            strategy_name=request.strategy_name,
        )

        execution_context = self._live_signal_evidence_context_uc.execute(
            run_at=datetime.now(IDX_TIMEZONE),
        )

        if request.multi:
            return self._execute_multi(request, request_builder, warnings, execution_context)

        return self._execute_single(request, request_builder, warnings, execution_context)

    def _execute_single(
        self,
        request: RunAccumulationScreenWorkflowRequest,
        request_builder: BuildSignalObservationScreenRequest,
        warnings: list[str],
        execution_context: SignalEvidenceExecutionContext,
    ) -> RunAccumulationScreenWorkflowResult:
        screen_request = request_builder.build(
            tickers=request.tickers,
            window_days=request.window,
        )
        response = self._screen_use_case.execute(
            screen_request,
            execution_context=execution_context,
        )

        display_cfg = self._accumulation_screener_config.display
        projection = project_single_screen_result(
            response,
            vwap_only=request.vwap_only,
            squeeze_only=request.squeeze_only,
            top=request.top,
            min_streak=request.min_streak,
            coiled_spring_bb_pctile=display_cfg.coiled_spring_bb_pctile,
            effective_session=execution_context.effective_session,
            sort_by=request.sort_by,
        )

        strategy_signals: dict[str, str] = {}
        if request.include_strategy_overlay:
            registry = self._indicator_registry_factory(
                broker_repository=self._broker_repository,
                market_repository=self._market_repository,
            )
            strat_loader = StrategyLoader(
                rules_loader=self._rules_loader, registry=registry
            )
            try:
                rules_path = strat_loader.resolve(request.strategy_name)
            except StrategyNotFoundError as e:
                warnings.append(f"Strategy not found: {e}")
                strategy_signals = {}
                # Do not return — fall through to save branch below.
                rules_path = None

            if rules_path is not None:
                risk_uc = AssessRiskUseCase(
                    repository=self._market_repository,
                    registry=registry,
                    rules_loader=self._rules_loader,
                )
                for c in projection.candidates:
                    try:
                        req = AssessRiskRequest(ticker=c.ticker, rules_file=rules_path)
                        res = risk_uc.execute(req)
                        strategy_signals[c.ticker] = res.assessment.risk_level_name
                    except Exception:
                        strategy_signals[c.ticker] = "?"

        save_result = None
        if (
            request.save_enabled
            and request.save_name is not None
            and self._save_watchlist_use_case is not None
        ):
            save_result = self._save_watchlist_use_case.execute(
                SaveScreenWatchlistRequest(
                    name=request.save_name,
                    candidates=projection.candidates,
                    universe=str(request.universe_name or ""),
                    window_days=request.window,
                )
            )

        return RunAccumulationScreenWorkflowResult(
            response=response,
            single_projection=projection,
            strategy_signals=strategy_signals,
            save_result=save_result,
            warnings=tuple(warnings),
        )

    def _execute_multi(
        self,
        request: RunAccumulationScreenWorkflowRequest,
        request_builder: BuildSignalObservationScreenRequest,
        warnings: list[str],
        execution_context: SignalEvidenceExecutionContext,
    ) -> RunAccumulationScreenWorkflowResult:
        validate_multi_window_request(request.windows, request.sort_by)

        # TODO(S7 follow-up): this still runs the full screen pipeline (incl.
        # SignalEngine/risk funnel/setup-phase) once per window instead of
        # computing 7/30/90 from one shared in-memory series. A true one-pass
        # implementation requires refactoring AccumulationScreenUseCase to
        # expose a window-only recompute path, which is out of scope here —
        # see tasks/backlog/saham_screen_improvements.md Task S7. The
        # canonical window's Signal/Risk/Phase/Data/Next are the only ones
        # surfaced to the user (project_multi_screen_result), so this
        # redundant work is wasted CPU, not wrong output.
        multi_builder = request_builder.with_score_filters_disabled()
        multi_results: dict[int, AccumulationScreenResponse] = {}
        for w in request.windows:
            multi_results[w] = self._screen_use_case.execute(
                multi_builder.build(
                    tickers=request.tickers,
                    window_days=w,
                ),
                execution_context=execution_context,
            )

        screened_at = next(iter(multi_results.values())).screened_at
        tracked_broker_flow = compute_tracked_broker_flow_batch(
            tickers=request.tickers,
            broker_repo=self._broker_repository,
            smart_money_brokers=self._swing_config.smart_money_brokers,
            noise_brokers=self._swing_config.noise_brokers,
            as_of_date=screened_at,
        )

        canonical_window = (
            _DEFAULT_MULTI_CANONICAL_WINDOW
            if _DEFAULT_MULTI_CANONICAL_WINDOW in request.windows
            else request.windows[0]
        )

        display_cfg = self._accumulation_screener_config.display
        multi_projection = project_multi_screen_result(
            multi_results,
            tracked_broker_flow=tracked_broker_flow,
            windows=request.windows,
            top=request.top,
            sort_by=request.sort_by,
            squeeze_only=request.squeeze_only,
            coiled_spring_min_foreign_flow_score=display_cfg.coiled_spring_min_foreign_flow_score,
            coiled_spring_bb_pctile=display_cfg.coiled_spring_bb_pctile,
            canonical_window=canonical_window,
            effective_session=execution_context.effective_session,
        )

        return RunAccumulationScreenWorkflowResult(
            multi_results=multi_results,
            multi_projection=multi_projection,
            tracked_broker_flow=tracked_broker_flow,
            warnings=tuple(warnings),
        )
