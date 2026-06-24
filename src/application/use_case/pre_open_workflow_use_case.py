"""
Application workflow coordinator for `saham screen pre-open`.

Layer: Application
AI usage: Optional, only when caller injects an AI-enabled PreOpenScreenUseCase.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
from src.application.services.universe_loader import resolve_tickers
from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from typing import TYPE_CHECKING

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
    benchmark: str = "^JKSE"
    db_path: Path = Path("data.db")
    signal_strategy: str | None = None


@dataclass(frozen=True)
class PreOpenWorkflowResponse:
    result: PreOpenScreenResult
    warnings: list[str]
    raw_movers: list
    data_freshness: PreOpenDataFreshness
    market_regime: "MarketContext | None" = None
    strategy_signals: dict[str, str] | None = None
    strategy_name: str | None = None


class PreOpenWorkflowUseCase:
    """Run the pre-open screen and attach deterministic workflow context."""

    def __init__(
        self,
        screen_use_case: PreOpenScreenUseCase,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        registry: IndicatorRegistry,
        market_context_engine=None,
    ) -> None:
        self._screen_use_case = screen_use_case
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._mce = market_context_engine

    def execute(self, request: PreOpenWorkflowRequest) -> PreOpenWorkflowResponse:
        screen_response = self._screen_use_case.execute(
            PreOpenScreenRequest(
                config=request.config,
                run_date=request.run_date,
            )
        )
        result = screen_response.result

        warnings = list(screen_response.warnings) + list(request.guard_warnings)
        strategy_signals, strategy_warning = self._build_strategy_signals(
            strategy_name=request.signal_strategy,
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
                market_regime = self._build_market_regime(
                    db_path=request.db_path,
                    as_of_date=result.screened_date,
                    universe=request.regime_universe,
                    benchmark=request.benchmark,
                )
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")

        return PreOpenWorkflowResponse(
            result=result,
            warnings=warnings,
            raw_movers=screen_response.raw_movers,
            data_freshness=data_freshness,
            market_regime=market_regime,
            strategy_signals=strategy_signals,
            strategy_name=request.signal_strategy,
        )

    def _build_strategy_signals(
        self,
        strategy_name: str | None,
        candidates: list[ScreenerCandidate],
    ) -> tuple[dict[str, str] | None, str | None]:
        if not strategy_name:
            return None, None

        try:
            strategy_loader = StrategyLoader(registry=self._registry)
            rules_path = strategy_loader.resolve(strategy_name)
        except StrategyNotFoundError as exc:
            return {}, f"Strategy '{strategy_name}' not found: {exc}"

        risk_use_case = AssessRiskUseCase(
            repository=self._market_repo,
            registry=self._registry,
        )
        signals: dict[str, str] = {}
        for candidate in candidates:
            try:
                response = risk_use_case.execute(
                    AssessRiskRequest(
                        ticker=candidate.ticker,
                        rules_file=rules_path,
                    )
                )
                signals[candidate.ticker] = response.assessment.risk_level_name
            except Exception:
                signals[candidate.ticker] = "?"
        return signals, None

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

    def _build_market_regime(
        self,
        db_path: Path,
        as_of_date: date,
        universe: str,
        benchmark: str,
    ) -> "MarketContext":
        if self._mce is not None:
            return self._mce.evaluate(as_of_date=as_of_date)

        # Fallback: construct MCE on demand when not injected
        from src.application.services.market_context_engine import MarketContextEngine
        from src.infrastructure.config.market_context_config import load_market_context_config
        from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
        from src.infrastructure.persistence.sqlite_market_context_repository import SQLiteMarketContextRepository
        from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

        tickers = resolve_tickers(universe=universe, explicit=[], db_path=db_path)
        engine = MarketContextEngine(
            market_repository=SQLiteMarketRepository(db_path=db_path),
            config=load_market_context_config(),
            universe=tickers,
            broker_repository=SQLiteBrokerRepository(db_path=db_path),
            context_repository=SQLiteMarketContextRepository(db_path=db_path),
        )
        return engine.evaluate(as_of_date=as_of_date)


def _min_latest_date(dates: list[date]) -> date | None:
    if not dates:
        return None
    return min(dates)
