"""
Workflow orchestration for saham screen accum command.

Owns multi-window orchestration, min-streak post-filter, broker-quality
computation, strategy-signal overlay, and watchlist save.  The CLI adapter
calls this single use case and renders the result.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.application.dto.accumulation_screen import AccumulationScreenResponse
from src.application.services.broker_quality import (
    BrokerQualitySnapshot,
    compute_broker_quality_batch,
)
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


@dataclass(frozen=True)
class RunAccumulationScreenWorkflowResult:
    response: AccumulationScreenResponse | None = None
    multi_results: dict[int, AccumulationScreenResponse] = field(default_factory=dict)
    broker_quality: dict[str, BrokerQualitySnapshot] = field(default_factory=dict)
    strategy_signals: dict[str, str] = field(default_factory=dict)
    save_result: SaveScreenWatchlistResult | None = None
    warnings: tuple[str, ...] = ()


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
        save_watchlist_use_case=None,
    ) -> None:
        self._screen_use_case = screen_use_case
        self._broker_repository = broker_repository
        self._market_repository = market_repository
        self._swing_config = swing_config
        self._accumulation_screener_config = accumulation_screener_config
        self._rules_loader = rules_loader
        self._indicator_registry_factory = indicator_registry_factory
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
            min_net_buy_days=max(1, request.min_streak),
            min_foreign_flow_score=request.min_foreign_flow_score,
            min_signal_score=request.min_signal_score,
            min_piotroski=request.min_piotroski,
            strategy_name=request.strategy_name,
        )

        if request.multi:
            return self._execute_multi(request, request_builder, warnings)

        return self._execute_single(request, request_builder, warnings)

    def _execute_single(
        self,
        request: RunAccumulationScreenWorkflowRequest,
        request_builder: BuildSignalObservationScreenRequest,
        warnings: list[str],
    ) -> RunAccumulationScreenWorkflowResult:
        screen_request = request_builder.build(
            tickers=request.tickers,
            window_days=request.window,
        )
        response = self._screen_use_case.execute(screen_request)

        if request.min_streak > 0:
            response.candidates = [
                c for c in response.candidates if c.consecutive_streak >= request.min_streak
            ]

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
                visible = response.candidates[:request.top]
                for c in visible:
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
                    candidates=response.candidates[:request.top],
                    universe=str(request.universe_name or ""),
                    window_days=request.window,
                )
            )

        return RunAccumulationScreenWorkflowResult(
            response=response,
            strategy_signals=strategy_signals,
            save_result=save_result,
            warnings=tuple(warnings),
        )

    def _execute_multi(
        self,
        request: RunAccumulationScreenWorkflowRequest,
        request_builder: BuildSignalObservationScreenRequest,
        warnings: list[str],
    ) -> RunAccumulationScreenWorkflowResult:
        multi_builder = request_builder.with_score_filters_disabled()
        multi_results: dict[int, AccumulationScreenResponse] = {}
        for w in request.windows:
            multi_results[w] = self._screen_use_case.execute(
                multi_builder.build(
                    tickers=request.tickers,
                    window_days=w,
                )
            )

        screened_at = next(iter(multi_results.values())).screened_at
        broker_quality = compute_broker_quality_batch(
            tickers=request.tickers,
            broker_repo=self._broker_repository,
            smart_money_brokers=self._swing_config.smart_money_brokers,
            noise_brokers=self._swing_config.noise_brokers,
            as_of_date=screened_at,
        )

        return RunAccumulationScreenWorkflowResult(
            multi_results=multi_results,
            broker_quality=broker_quality,
            warnings=tuple(warnings),
        )
