"""Lazy serialized capability boundary and exact Phase 3 requests.

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Any

from src.adapters.tui.ticker_refresh_mode import TickerRefreshMode
from src.application.dto.swing_analysis import SwingAnalysisWorkflowRequest
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
    RunAccumulationScreenWorkflowUseCase,
)
from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisWorkflowUseCase,
)


@dataclass(frozen=True)
class ResearchExecution:
    accumulation: RunAccumulationScreenWorkflowUseCase
    # Keyed by selected setup name; the ``None`` key is the no-setup workflow.
    # Each workflow bakes its own ``evaluate_setup`` so setup selection routes to
    # the matching workflow instead of mutating one shared instance.
    swing_workflows: dict[str | None, SwingAnalysisWorkflowUseCase]
    config: Any
    db_path: Path
    tickers: list[str]
    flow_window: int
    universe_resolver: Callable[[str], list[str]] | None = None


class SerializedResearchCapabilities:
    def __init__(self, factory: Callable[[], ResearchExecution]) -> None:
        self._factory = factory
        self._execution: ResearchExecution | None = None
        self._lock = Lock()

    def load_accumulation(self, request: RunAccumulationScreenWorkflowRequest | bool):
        with self._lock:
            execution = self._get_execution()
            if isinstance(request, bool):
                req = build_accumulation_request(execution.config, execution.tickers, request)
            else:
                tickers = request.tickers
                if not tickers and execution.universe_resolver is not None:
                    uni_name = (request.universe_name or request.universe_label or "lq45").lower()
                    tickers = execution.universe_resolver(uni_name)
                if not tickers:
                    tickers = execution.tickers
                req = _clone_request_with_tickers(request, tickers)
            return execution.accumulation.execute(req)

    def load_ticker(
        self,
        ticker: str,
        mode: TickerRefreshMode = TickerRefreshMode.CACHED_ONLY,
        setup: str | None = None,
    ):
        with self._lock:
            execution = self._get_execution()
            workflow = execution.swing_workflows.get(setup)
            if workflow is None:
                raise ValueError(f"No swing workflow wired for setup {setup!r}")
            return workflow.execute(
                build_ticker_request(
                    execution.config,
                    execution.db_path,
                    execution.flow_window,
                    ticker,
                    mode=mode,
                    setup=setup,
                )
            )

    def _get_execution(self) -> ResearchExecution:
        if self._execution is None:
            self._execution = self._factory()
        return self._execution


def build_accumulation_request(
    config: Any, tickers: list[str], multi: bool
) -> RunAccumulationScreenWorkflowRequest:
    universe = config.analysis.universe
    return RunAccumulationScreenWorkflowRequest(
        tickers=tickers,
        universe_label=universe,
        universe_name=universe,
        window=7,
        min_streak=0,
        min_accum_score=None,
        min_signal_score=None,
        min_piotroski=0,
        strategy_name=None,
        include_strategy_overlay=False,
        multi=multi,
        windows=[7, 30, 90] if multi else [],
        top=20,
        save_name=None,
        save_enabled=False,
        vwap_only=False,
        squeeze_only=False,
        sort_by="vwap",
    )


def _clone_request_with_tickers(
    req: RunAccumulationScreenWorkflowRequest, tickers: list[str]
) -> RunAccumulationScreenWorkflowRequest:
    return RunAccumulationScreenWorkflowRequest(
        tickers=tickers,
        universe_label=req.universe_label,
        universe_name=req.universe_name,
        window=req.window,
        min_streak=req.min_streak,
        min_accum_score=req.min_accum_score,
        min_signal_score=req.min_signal_score,
        min_piotroski=req.min_piotroski,
        strategy_name=req.strategy_name,
        include_strategy_overlay=req.include_strategy_overlay,
        multi=req.multi,
        windows=req.windows,
        top=req.top,
        save_name=req.save_name,
        save_enabled=req.save_enabled,
        squeeze_only=req.squeeze_only,
        vwap_only=req.vwap_only,
        sort_by=req.sort_by,
    )


def build_ticker_request(
    config: Any,
    db_path: Path,
    flow_window: int,
    ticker: str,
    *,
    mode: TickerRefreshMode = TickerRefreshMode.CACHED_ONLY,
    setup: str | None = None,
) -> SwingAnalysisWorkflowRequest:
    # The one place UI intent becomes provider flags. Cached only never sets
    # auto_refresh, so it cannot reach the refresh capability at all.
    auto_refresh, force_refresh = mode.flags
    return SwingAnalysisWorkflowRequest(
        ticker=ticker,
        today=date.today(),
        strategy_name=None,
        setup_name=setup,
        window=config.swing.window,
        flow_window=flow_window,
        capital=None,
        risk_pct=config.swing.risk_pct,
        entry_price=None,
        atr_mult=config.swing.atr_mult,
        rr=config.swing.rr,
        include_sentiment=False,
        include_flow_detail=setup is not None,
        include_signal_detail=False,
        include_risk_detail=False,
        include_market_detail=False,
        sentiment_verbose=False,
        auto_refresh=auto_refresh,
        force_refresh=force_refresh,
        with_market_context=False,
        regime_universe=config.analysis.regime_universe,
        benchmark=config.analysis.benchmark,
        db_path=db_path,
        with_technical_gate=False,
    )
