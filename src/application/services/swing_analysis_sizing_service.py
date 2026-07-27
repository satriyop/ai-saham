"""Position sizing phase for swing analysis workflow.

Layer: Application

Owns ATR calculation, ATR-based position sizing, setup entry selection,
setup percent sizing, and swing target resolution. Extracted from
`SwingAnalysisWorkflowUseCase` to keep the use case as orchestration only.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from src.application.dto import swing_analysis as swing_analysis_dto
from src.application.services.position_sizer import (
    compute_percent_position_size,
    compute_position_size,
)
from src.application.services.swing_analysis_atr import compute_swing_atr
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)


class SwingAnalysisSizingService:
    """Owns ATR calculation, position sizing, and swing target resolution."""

    def __init__(
        self,
        registry: Any,
        load_swing_config: Callable[[], Any],
        resolve_setup_targets: Callable[[str | None, Any], tuple[Decimal, Decimal]],
    ) -> None:
        self._registry = registry
        self._load_swing_config = load_swing_config
        self._resolve_setup_targets = resolve_setup_targets

    def compute_atr(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
        state.atr_value = compute_swing_atr(self._registry, state.candles)
        return state

    def compute_entry_sizing(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
        setup_entry: Decimal | None = None
        sizing = None
        if request.capital is not None and state.setup_eval is not None and state.setup_eval.passed:
            setup_entry = (
                Decimal(str(request.entry_price)) if request.entry_price else state.latest_close
            )
        elif request.capital is not None and state.atr_value and state.setup_eval is None:
            try:
                entry = (
                    Decimal(str(request.entry_price)) if request.entry_price else state.latest_close
                )
                sizing = compute_position_size(
                    entry=entry,
                    atr=state.atr_value,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    atr_multiplier=Decimal(str(request.atr_mult)),
                    reward_risk=Decimal(str(request.rr)),
                )
            except ValueError as exc:
                state.warnings.append(f"Position sizing unavailable: {exc}")

        state.setup_entry = setup_entry
        state.sizing = sizing
        return state

    def resolve_targets_and_percent_sizing(
        self,
        request: swing_analysis_dto.SwingAnalysisWorkflowRequest,
        state: SwingAnalysisWorkflowState,
    ) -> SwingAnalysisWorkflowState:
        swing_config = self._load_swing_config()
        regime_label = state.market_regime.regime.value if state.market_regime else None
        take_profit_pct, stop_loss_pct = self._resolve_setup_targets(
            regime_label,
            swing_config,
        )

        setup_sizing = None
        if state.setup_entry is not None and request.capital is not None:
            try:
                setup_sizing = compute_percent_position_size(
                    entry=state.setup_entry,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                )
            except ValueError as exc:
                state.warnings.append(f"Setup sizing unavailable: {exc}")

        state.swing_config = swing_config
        state.regime_label = regime_label
        state.take_profit_pct = take_profit_pct
        state.stop_loss_pct = stop_loss_pct
        state.setup_sizing = setup_sizing
        return state
