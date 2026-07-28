"""
Application workflow: orchestrates swing candidate logging and setup policy validation.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from src.application.dto.swing_policy_config import SwingPolicyConfig
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.evaluate_swing_setup_use_case import SwingSetupCatalogConfig
from src.application.use_case.log_swing_candidate_use_case import (
    LogSwingCandidateRequest,
    LogSwingCandidateResponse,
    LogSwingCandidateUseCase,
)


class SwingBacktestConfig(Protocol):
    """Protocol defining required attributes from infrastructure backtest config."""

    take_profit_pct: float
    stop_loss_pct: float
    max_hold_days: int


@dataclass(frozen=True)
class LogAccumulationTradeWorkflowRequest:
    ticker: str
    window: int
    entry_price: Decimal | None
    from_analysis: bool
    setup: str
    with_regime: bool
    benchmark: str
    logged_at: date
    # ADR-054 S5: frozen geometry from swing_trade_plan
    from_plan: bool = False
    plan_entry: Decimal | None = None
    plan_stop: Decimal | None = None
    plan_target: Decimal | None = None
    plan_setup_match: str | None = None
    plan_max_hold_days: int | None = None


@dataclass(frozen=True)
class LogAccumulationTradePolicy:
    tier1_broker_codes: frozenset[str]
    sector_breadth_enabled: bool
    sector_breadth_threshold: float
    sector_breadth_bonus_pts: float
    sector_breadth_min_tickers: int
    setup_config: SwingSetupCatalogConfig
    resistance_gate_enabled: bool
    resistance_headroom_min_pct: float
    ex_date_warning_days: int
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    max_hold_days: int


@dataclass(frozen=True)
class LogAccumulationTradeWorkflowResult:
    response: LogSwingCandidateResponse
    setup_name: str
    logged_at: date
    max_hold_days: int


@dataclass(frozen=True)
class LogAccumulationTradeWorkflowBundle:
    workflow: "LogAccumulationTradeWorkflowUseCase"
    warnings: tuple[str, ...] = ()


def build_log_accumulation_trade_policy(
    swing_policy: SwingPolicyConfig,
    backtest_config: SwingBacktestConfig,
) -> LogAccumulationTradePolicy:
    """Build the workflow policy from swing config and backtest defaults."""
    default_target = swing_policy.setup_targets.get("default")

    take_profit = (
        default_target.take_profit_pct
        if default_target is not None
        else Decimal(str(backtest_config.take_profit_pct))
    )
    stop_loss = (
        default_target.stop_loss_pct
        if default_target is not None
        else Decimal(str(backtest_config.stop_loss_pct))
    )

    setup_config = build_swing_setup_catalog_config(swing_policy)

    return LogAccumulationTradePolicy(
        tier1_broker_codes=swing_policy.tier1_broker_codes,
        sector_breadth_enabled=swing_policy.sector_breadth_enabled,
        sector_breadth_threshold=swing_policy.sector_breadth_threshold,
        sector_breadth_bonus_pts=swing_policy.sector_breadth_bonus_pts,
        sector_breadth_min_tickers=swing_policy.sector_breadth_min_tickers,
        setup_config=setup_config,
        resistance_gate_enabled=swing_policy.resistance_gate_enabled,
        resistance_headroom_min_pct=swing_policy.resistance_headroom_min_pct,
        ex_date_warning_days=swing_policy.ex_date_warning_days,
        take_profit_pct=take_profit,
        stop_loss_pct=stop_loss,
        max_hold_days=backtest_config.max_hold_days,
    )


class LogAccumulationTradeWorkflowUseCase:
    def __init__(
        self,
        log_use_case: LogSwingCandidateUseCase,
        policy: LogAccumulationTradePolicy,
        available_setups: tuple[str, ...],
    ) -> None:
        self._policy = policy
        self._log_use_case = log_use_case
        self._available_setups = available_setups

    def execute(
        self,
        request: LogAccumulationTradeWorkflowRequest,
    ) -> LogAccumulationTradeWorkflowResult:
        ticker_upper = request.ticker.upper()
        setup_name = request.setup.lower()

        if request.from_analysis and not request.from_plan:
            if setup_name not in self._available_setups:
                raise ValueError(
                    f"Unknown swing setup '{request.setup}'. "
                    f"Available setups: {', '.join(self._available_setups)}"
                )
            setup_val = setup_name
        elif request.from_plan:
            setup_val = setup_name if setup_name in self._available_setups else request.setup
        else:
            setup_val = None

        candidate_request = LogSwingCandidateRequest(
            ticker=ticker_upper,
            window_days=request.window,
            entry_price=request.entry_price,
            from_analysis=request.from_analysis and not request.from_plan,
            setup=setup_val,
            with_regime=request.with_regime,
            regime_universe=[],
            benchmark_ticker=request.benchmark,
            logged_at=request.logged_at,
            tier1_broker_codes=self._policy.tier1_broker_codes,
            sector_breadth_enabled=self._policy.sector_breadth_enabled,
            sector_breadth_threshold=self._policy.sector_breadth_threshold,
            sector_breadth_bonus_pts=self._policy.sector_breadth_bonus_pts,
            sector_breadth_min_tickers=self._policy.sector_breadth_min_tickers,
            setup_config=self._policy.setup_config,
            resistance_gate_enabled=self._policy.resistance_gate_enabled,
            resistance_headroom_min_pct=self._policy.resistance_headroom_min_pct,
            ex_date_warning_days=self._policy.ex_date_warning_days,
            take_profit_pct=self._policy.take_profit_pct,
            stop_loss_pct=self._policy.stop_loss_pct,
            max_hold_days=self._policy.max_hold_days,
            from_plan=request.from_plan,
            plan_entry=request.plan_entry,
            plan_stop=request.plan_stop,
            plan_target=request.plan_target,
            plan_setup_match=request.plan_setup_match,
            plan_max_hold_days=request.plan_max_hold_days,
        )

        response = self._log_use_case.execute(candidate_request)
        hold = (
            request.plan_max_hold_days
            if request.from_plan and request.plan_max_hold_days is not None
            else self._policy.max_hold_days
        )
        return LogAccumulationTradeWorkflowResult(
            response=response,
            setup_name=setup_name,
            logged_at=request.logged_at,
            max_hold_days=hold,
        )
