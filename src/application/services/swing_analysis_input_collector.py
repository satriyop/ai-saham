"""Input collection phase for swing analysis workflow.

Layer: Application

Owns auto-refresh, data freshness, optional flow/broker detail, candle
loading, accumulation-candidate build, and market-context evaluation.
Extracted from `SwingAnalysisWorkflowUseCase` to keep the use case as
orchestration only.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker

if TYPE_CHECKING:
    from src.application.dto import swing_analysis as swing_analysis_dto
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.market_context import MarketContext


class SwingAnalysisDataUnavailable(Exception):
    """Raised when a ticker has no local candle data for swing analysis."""

    def __init__(self, ticker: str) -> None:
        super().__init__(ticker)
        self.ticker = ticker


class SwingAnalysisInputCollector:
    """Collects raw inputs needed before decision composition."""

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        broker_repository: "BrokerDataRepository",
        refresh_data: Callable[..., tuple[str, ...]],
        build_data_freshness: Callable[..., Any],
        build_flow_detail: Callable[..., Any],
        build_broker_detail: Callable[..., Any],
        build_accumulation_candidate: Callable[..., Any | None],
        evaluate_market_context: Callable[..., "MarketContext"] | None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._refresh_data = refresh_data
        self._build_data_freshness = build_data_freshness
        self._build_flow_detail = build_flow_detail
        self._build_broker_detail = build_broker_detail
        self._build_accumulation_candidate = build_accumulation_candidate
        self._evaluate_market_context = evaluate_market_context

    def collect(
        self, request: "swing_analysis_dto.SwingAnalysisWorkflowRequest"
    ) -> SwingAnalysisWorkflowState:
        warnings: list[str] = []

        refresh_actions = ("disabled",)
        if request.auto_refresh:
            refresh_actions = self._refresh_data(
                ticker=request.ticker,
                db_path=request.db_path,
                force_refresh=request.force_refresh,
            )

        data_freshness = self._build_data_freshness(
            ticker=request.ticker,
            as_of_date=request.today,
            market_repo=self._market_repo,
            broker_repo=self._broker_repo,
            refresh_actions=refresh_actions,
        )
        needs_broker_detail = request.include_flow_detail or request.setup_name is not None
        flow_detail = None
        if request.include_flow_detail:
            flow_detail = self._build_flow_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=request.flow_window,
                as_of_date=request.today,
            )
        broker_detail = None
        if needs_broker_detail:
            broker_detail = self._build_broker_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=5,
                as_of_date=request.today,
            )

        candles = self._market_repo.get_candles(request.ticker)
        if not candles:
            raise SwingAnalysisDataUnavailable(request.ticker)
        latest_close = candles[-1].close

        accumulation_candidate = None
        try:
            accumulation_candidate = self._build_accumulation_candidate(
                ticker=request.ticker,
                window=request.window,
            )
        except Exception as exc:
            warnings.append(f"Accumulation unavailable: {exc}")

        market_regime = None
        if request.with_market_context:
            try:
                if self._evaluate_market_context is None:
                    raise RuntimeError("Market context evaluator is not configured.")
                market_regime = self._evaluate_market_context(
                    db_path=request.db_path,
                    as_of_date=request.today,
                    universe=request.regime_universe,
                    benchmark=canonicalize_ticker(request.benchmark),
                )
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")

        return SwingAnalysisWorkflowState(
            warnings=warnings,
            refresh_actions=refresh_actions,
            data_freshness=data_freshness,
            flow_detail=flow_detail,
            broker_detail=broker_detail,
            candles=candles,
            latest_close=latest_close,
            accumulation_candidate=accumulation_candidate,
            market_regime=market_regime,
        )
