"""Walk-forward portfolio backtest for deterministic swing trade setups.

Layer: Application
Depends on: Domain ports and services
AI usage: None
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationDerivedFeaturePolicy,
    AccumulationScreenRequest,
)
from src.application.dto.swing_backtest import (
    DEFAULT_SWING_COST_BPS,
    FOREIGN_BOUNCE_SETUP,
    SwingBacktestCandidateObservation,
    SwingBacktestDailyEquity,
    SwingBacktestEntrySignal,
    SwingBacktestRegimeStat,
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestTrade,
)
from src.application.ports.market_context_provider import MarketContextProvider
from src.application.services.backtest_statistics import (
    average_pct,
    equity_max_drawdown_pct,
    pct_change_pct,
    trade_profit_factor,
    win_rate_pct,
)
from src.application.services.swing_backtest_attribution import (
    summarize_swing_backtest_attribution,
)
from src.application.services.swing_backtest_exit_engine import SwingBacktestExitEngine
from src.application.services.swing_backtest_observation_builder import (
    SwingBacktestObservationBuilder,
)
from src.application.services.swing_backtest_position_builder import SwingBacktestPositionBuilder
from src.application.services.swing_backtest_simulator import SwingBacktestSimulator
from src.application.services.swing_backtest_trade_setup_attributor import (
    SwingBacktestTradeSetupAttributor,
)
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.setup_evaluation import SetupEvaluation

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_SWING_COST_BPS",
    "FOREIGN_BOUNCE_SETUP",
    "SwingBacktestCandidateObservation",
    "SwingBacktestDailyEquity",
    "SwingBacktestRegimeStat",
    "SwingBacktestRequest",
    "SwingBacktestResponse",
    "SwingBacktestTrade",
    "SwingBacktestUseCase",
]


class SwingBacktestUseCase:
    """Simulate the actual daily swing workflow with portfolio constraints.

    The simulation is deterministic and local-only. Signals are generated from
    data available as of each replay date, entries use that date's close, and
    exits are evaluated on later candles only.
    """

    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
        derived_feature_policy: AccumulationDerivedFeaturePolicy | None = None,
        risk_engine: Any | None = None,
        market_context_provider: MarketContextProvider | None = None,
    ) -> None:
        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._derived_features = derived_feature_policy or AccumulationDerivedFeaturePolicy()
        self._screen = AccumulationScreenUseCase(
            broker_repository=broker_repository,
            market_repository=market_repository,
            derived_feature_policy=self._derived_features,
        )
        self._market_context_provider = market_context_provider
        self._attributor = SwingBacktestTradeSetupAttributor(
            risk_engine=risk_engine,
        )
        self._observation_builder = SwingBacktestObservationBuilder(
            market_repository=market_repository,
            trade_setup_attributor=self._attributor,
        )
        self._position_builder = SwingBacktestPositionBuilder(
            trade_setup_attributor=self._attributor,
        )
        self._exit_engine = SwingBacktestExitEngine(
            market_repository=market_repository,
        )
        self._simulator = SwingBacktestSimulator(
            market_repository=market_repository,
            position_builder=self._position_builder,
            exit_engine=self._exit_engine,
        )

    def execute(self, request: SwingBacktestRequest) -> SwingBacktestResponse:
        self._validate(request)
        tickers = [ticker.upper().strip() for ticker in request.tickers if ticker.strip()]
        replay_dates = self._replay_dates(tickers, request.start_date, request.end_date)
        regime_by_date = self._regime_by_date(tickers, replay_dates, request)

        # Pre-build entry signals per date to decouple simulator from screening
        signals_by_date: dict[date, list[SwingBacktestEntrySignal]] = {}
        for current_date in replay_dates:
            regime = regime_by_date.get(current_date)
            signals_by_date[current_date] = self._signals_for_date(
                tickers,
                current_date,
                request,
                regime,
            )

        sim_result = self._simulator.run(
            replay_dates=replay_dates,
            request=request,
            signals_by_date=signals_by_date,
            regime_by_date=regime_by_date,
        )

        return SwingBacktestResponse(
            setup=request.setup,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.capital,
            cost_bps=request.cost_bps,
            final_equity=sim_result.final_equity,
            total_return_pct=pct_change_pct(sim_result.final_equity, request.capital),
            max_drawdown_pct=equity_max_drawdown_pct(sim_result.equity_curve),
            trade_count=len(sim_result.trades),
            win_rate_pct=win_rate_pct([float(t.pnl) for t in sim_result.trades]),
            avg_trade_return_pct=average_pct([t.net_return_pct for t in sim_result.trades]),
            profit_factor=trade_profit_factor(sim_result.trades),
            exposure_pct=round(sim_result.exposure_days / len(replay_dates) * 100, 2)
            if replay_dates
            else 0.0,
            skipped_no_cash=sim_result.skipped_no_cash,
            skipped_duplicate=sim_result.skipped_duplicate,
            skipped_no_forward_data=sim_result.skipped_no_forward_data,
            skipped_by_regime=sim_result.skipped_by_regime,
            trades=sim_result.trades,
            candidate_observations=sim_result.candidate_observations,
            equity_curve=sim_result.equity_curve,
            regime_stats=self._regime_stats(sim_result.trades),
            regime_by_date=regime_by_date,
            attribution_summary=summarize_swing_backtest_attribution(
                sim_result.trades,
                sim_result.candidate_observations,
                request.attribution_bucket_policy,
            ),
            warnings=[
                "Backtest uses the supplied current universe; "
                "historical index membership is not reconstructed.",
                "Signals enter at same-day close; intraday execution/slippage is not modeled.",
                f"Same-day stop/target priority: {request.same_day_exit_priority}.",
            ],
        )

    def _validate(self, request: SwingBacktestRequest) -> None:
        if request.setup not in AVAILABLE_SWING_SETUPS:
            raise ValueError(f"Unsupported swing setup: {request.setup}")
        if not request.tickers:
            raise ValueError("At least one ticker is required")
        if request.start_date > request.end_date:
            raise ValueError("start_date must be on or before end_date")
        if request.capital <= 0:
            raise ValueError("capital must be positive")
        if request.risk_pct <= 0:
            raise ValueError("risk_pct must be positive")
        if request.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if request.take_profit_pct <= 0 or request.stop_loss_pct <= 0:
            raise ValueError("take profit and stop loss must be positive")
        if request.max_hold_days <= 0:
            raise ValueError("max_hold_days must be positive")
        if request.cost_bps < 0:
            raise ValueError("cost_bps cannot be negative")
        if request.forward_data_lookahead_days <= 0:
            raise ValueError("forward_data_lookahead_days must be positive")
        if request.same_day_exit_priority not in {"stop_first", "target_first"}:
            raise ValueError("same_day_exit_priority must be stop_first or target_first")
        valid_regimes = {"RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE"}
        invalid = [r for r in request.allowed_regimes if r.upper() not in valid_regimes]
        if invalid:
            raise ValueError(
                "allowed_regimes must contain only: RISK_ON, NEUTRAL, RISK_OFF, VOLATILE"
            )

    def _signals_for_date(
        self,
        tickers: list[str],
        signal_date: date,
        request: SwingBacktestRequest,
        market_context: MarketContext | None = None,
    ) -> list[SwingBacktestEntrySignal]:
        response = self._screen.execute(AccumulationScreenRequest(
            tickers=tickers,
            window_days=request.window_days,
            min_net_buy_days=request.min_net_buy_days,
            min_foreign_flow_score=0.0,
            min_foreign_flow_score_enabled=True,
            rsi_period=self._derived_features.rsi_period,
            sma_period=self._derived_features.trend_sma_period,
            as_of_date=signal_date,
            resistance_gate_enabled=request.resistance_gate_enabled,
            resistance_headroom_min_pct=request.resistance_headroom_min_pct,
            ex_date_warning_days=request.ex_date_warning_days,
        ))
        candidates = []
        for candidate in response.candidates:
            setup_evaluation = self._evaluate_setup(candidate, request)
            observation = self._observation_builder.build(
                candidate,
                setup_evaluation,
                signal_date,
                request,
                market_context,
            )
            candidates.append(SwingBacktestEntrySignal(candidate, setup_evaluation, observation))
        return sorted(
            candidates,
            key=lambda signal: (
                signal.candidate.foreign_flow_score,
                signal.candidate.avg_flow_ratio or 0.0,
                signal.candidate.vwap_discount_pct or 0.0,
            ),
            reverse=True,
        )

    def _evaluate_setup(
        self,
        candidate: AccumulationCandidate,
        request: SwingBacktestRequest,
    ) -> SetupEvaluation:
        return EvaluateSwingSetupUseCase().execute(
            EvaluateSwingSetupRequest(
                setup_name=request.setup,
                candidate=candidate,
                config=request.setup_config,
            )
        )

    def _replay_dates(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> list[date]:
        dates: set[date] = set()
        for ticker in tickers:
            candles = self._market_repo.get_candles(
                ticker,
                start_date=start_date,
                end_date=end_date,
            )
            dates.update(c.date for c in candles)
        return sorted(dates)

    def _regime_by_date(
        self,
        tickers: list[str],
        replay_dates: list[date],
        request: SwingBacktestRequest,
    ) -> dict[date, MarketContext]:
        if not request.include_regime and not request.allowed_regimes:
            return {}

        if self._market_context_provider is None:
            raise ValueError(
                "market_context_provider is required when include_regime=True "
                "or allowed_regimes is non-empty"
            )

        return self._market_context_provider.evaluate_for_dates(
            tickers=tickers,
            replay_dates=replay_dates,
            benchmark_ticker=request.benchmark_ticker,
        )

    def _regime_stats(
        self,
        trades: list[SwingBacktestTrade],
    ) -> list[SwingBacktestRegimeStat]:
        buckets: dict[str, list[SwingBacktestTrade]] = {}
        for trade in trades:
            if trade.regime is None:
                continue
            buckets.setdefault(trade.regime, []).append(trade)

        stats = [
            SwingBacktestRegimeStat(
                regime=regime,
                count=len(rows),
                avg_return_pct=average_pct([trade.net_return_pct for trade in rows]),
                win_rate_pct=win_rate_pct([float(trade.pnl) for trade in rows]),
                total_pnl=sum((trade.pnl for trade in rows), Decimal("0")),
            )
            for regime, rows in buckets.items()
        ]
        return sorted(stats, key=lambda s: s.count, reverse=True)
