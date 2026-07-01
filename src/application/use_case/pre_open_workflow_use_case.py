"""
Application workflow coordinator for `saham screen pre-open`.

Layer: Application
AI usage: Optional, only when caller injects an AI-enabled PreOpenScreenUseCase.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from collections.abc import Callable

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from typing import TYPE_CHECKING

from src.domain.value_objects.benchmark_symbol import canonicalize_ticker

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext
from src.application.use_case.pre_open_screen_use_case import (
    PreOpenScreenConfig,
    PreOpenScreenRequest,
    PreOpenScreenUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.screener_result import (
    PreOpenScreenResult,
    ScreenerCandidate,
)


@dataclass(frozen=True)
class PreOpenDataFreshness:
    """Data-source dates used by the pre-open screen."""

    analysis_date: date
    candle_end: date | None
    broker_end: date | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreOpenWorkflowRequest:
    config: PreOpenScreenConfig
    run_date: date
    guard_warnings: tuple[str, ...] = ()
    with_regime: bool = False
    regime_universe: str = "idx80"
    benchmark: str = "IHSG"
    db_path: Path = Path("data.db")
    risk_strategy: str | None = None


@dataclass(frozen=True)
class PreOpenWorkflowResponse:
    result: PreOpenScreenResult
    warnings: list[str]
    raw_movers: list
    data_freshness: PreOpenDataFreshness
    market_regime: "MarketContext | None" = None
    strategy_risk_statuses: dict[str, str] | None = None
    risk_strategy_name: str | None = None


class PreOpenWorkflowUseCase:
    """Run the pre-open screen and attach deterministic workflow context."""

    def __init__(
        self,
        screen_use_case: PreOpenScreenUseCase,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        registry: IndicatorRegistry,
        evaluate_market_context: Callable[..., "MarketContext"] | None = None,
    ) -> None:
        self._screen_use_case = screen_use_case
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._evaluate_market_context = evaluate_market_context

    def execute(self, request: PreOpenWorkflowRequest) -> PreOpenWorkflowResponse:
        screen_response = self._screen_use_case.execute(
            PreOpenScreenRequest(
                config=request.config,
                run_date=request.run_date,
            )
        )
        result = screen_response.result

        warnings = list(screen_response.warnings) + list(request.guard_warnings)
        strategy_risk_statuses, strategy_warning = self._build_strategy_risk_statuses(
            risk_strategy_name=request.risk_strategy,
            candidates=result.candidates,
        )
        if strategy_warning:
            warnings.append(strategy_warning)

        data_freshness = self._build_data_freshness(
            candidates=result.candidates,
            analysis_date=result.screened_date,
        )

        market_regime = None
        if request.with_regime:
            try:
                if self._evaluate_market_context is None:
                    raise RuntimeError("Market context evaluator is not configured.")
                market_regime = self._evaluate_market_context(
                    db_path=request.db_path,
                    as_of_date=result.screened_date,
                    universe=request.regime_universe,
                    benchmark=canonicalize_ticker(request.benchmark),
                )
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")

        return PreOpenWorkflowResponse(
            result=result,
            warnings=warnings,
            raw_movers=screen_response.raw_movers,
            data_freshness=data_freshness,
            market_regime=market_regime,
            strategy_risk_statuses=strategy_risk_statuses,
            risk_strategy_name=request.risk_strategy,
        )

    def _build_strategy_risk_statuses(
        self,
        risk_strategy_name: str | None,
        candidates: list[ScreenerCandidate],
    ) -> tuple[dict[str, str] | None, str | None]:
        if not risk_strategy_name:
            return None, None

        try:
            strategy_loader = StrategyLoader(registry=self._registry)
            rules_path = strategy_loader.resolve(risk_strategy_name)
        except StrategyNotFoundError as exc:
            return {}, f"Strategy '{risk_strategy_name}' not found: {exc}"

        risk_use_case = AssessRiskUseCase(
            repository=self._market_repo,
            registry=self._registry,
        )
        statuses: dict[str, str] = {}
        for candidate in candidates:
            try:
                response = risk_use_case.execute(
                    AssessRiskRequest(
                        ticker=candidate.ticker,
                        rules_file=rules_path,
                    )
                )
                statuses[candidate.ticker] = response.assessment.risk_level_name
            except Exception:
                statuses[candidate.ticker] = "?"
        return statuses, None

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
