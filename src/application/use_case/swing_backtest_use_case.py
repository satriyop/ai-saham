"""
Walk-forward portfolio backtest for deterministic swing trade setups.

Layer: Application
Depends on: Domain ports and accumulation screen use case
AI usage: None
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from src.application.services.market_context_engine import MarketContextEngine
from src.application.services.stats import (
    average,
    max_drawdown_pct,
    pct_change,
    profit_factor,
    win_rate,
)
from src.application.services.swing_backtest_attribution import (
    AttributionBucketPolicy,
    SwingBacktestAttributionSummary,
    summarize_swing_backtest_attribution,
)
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
    AccumulationDerivedFeaturePolicy,
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
)
from src.application.use_case.assess_trade_setup_use_case import (
    AssessTradeSetupRequest,
    AssessTradeSetupUseCase,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
    SwingSetupCatalogConfig,
)
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import GateContext
from src.domain.value_objects.idx_market import SHARES_PER_LOT
from src.domain.value_objects.market_context import MarketContext
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupGate

FOREIGN_BOUNCE_SETUP = "foreign-bounce"
DEFAULT_SWING_COST_BPS = Decimal("20")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SwingBacktestRequest:
    """Input parameters for a walk-forward swing workflow backtest."""

    tickers: list[str]
    start_date: date
    end_date: date
    setup: str = FOREIGN_BOUNCE_SETUP
    capital: Decimal = Decimal("100000000")
    risk_pct: Decimal = Decimal("0.01")
    max_positions: int = 5
    window_days: int = 7
    min_net_buy_days: int = 2
    min_vwap_disc_pct: float = 3.0
    trend: str = "SIDE"
    min_flow_pct: float = 5.0
    max_rsi: float = 60.0
    take_profit_pct: Decimal = Decimal("5")
    stop_loss_pct: Decimal = Decimal("5")
    max_hold_days: int = 10
    cost_bps: Decimal = DEFAULT_SWING_COST_BPS
    include_regime: bool = False
    benchmark_ticker: str = "^JKSE"
    allowed_regimes: tuple[str, ...] = ()
    setup_targets: dict[str, Any] | None = None
    setup_config: SwingSetupCatalogConfig = field(default_factory=SwingSetupCatalogConfig)
    resistance_gate_enabled: bool = True
    resistance_headroom_min_pct: float = 5.0
    ex_date_warning_days: int = 10
    forward_data_lookahead_days: int = 45
    same_day_exit_priority: str = "stop_first"
    attribution_bucket_policy: AttributionBucketPolicy = field(
        default_factory=AttributionBucketPolicy
    )


@dataclass(frozen=True)
class SwingBacktestTrade:
    """One completed walk-forward swing trade."""

    ticker: str
    entry_date: date
    exit_date: date
    entry_price: Decimal
    exit_price: Decimal
    lots: int
    shares: int
    entry_value: Decimal
    exit_value: Decimal
    gross_return_pct: float
    net_return_pct: float
    pnl: Decimal
    holding_days: int
    exit_reason: str
    foreign_flow_score: float
    flow_pct: float | None
    vwap_disc_pct: float | None
    rsi: float | None
    regime: str | None = None
    setup_match: str | None = None
    setup_failed_reasons: tuple[str, ...] = ()
    setup_gates: tuple[SetupGate, ...] = ()
    trade_setup_action: str | None = None
    signal_score: int | None = None
    signal_strength: str | None = None
    signal_entry_quality: str | None = None
    signal_breakdown: tuple[tuple[str, float], ...] = ()
    risk_status: str | None = None
    risk_gate: str | None = None
    risk_confidence: int | None = None
    market_context: MarketContext | None = None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "entry_date": self.entry_date.isoformat(),
            "exit_date": self.exit_date.isoformat(),
            "entry_price": str(self.entry_price),
            "exit_price": str(self.exit_price),
            "lots": self.lots,
            "shares": self.shares,
            "entry_value": str(self.entry_value),
            "exit_value": str(self.exit_value),
            "gross_return_pct": self.gross_return_pct,
            "net_return_pct": self.net_return_pct,
            "pnl": str(self.pnl),
            "holding_days": self.holding_days,
            "exit_reason": self.exit_reason,
            "foreign_flow_score": self.foreign_flow_score,
            "flow_pct": self.flow_pct,
            "vwap_disc_pct": self.vwap_disc_pct,
            "rsi": self.rsi,
            "regime": self.regime,
            "setup_match": self.setup_match,
            "setup_failed_reasons": list(self.setup_failed_reasons),
            "setup_gates": [
                {
                    "label": gate.label,
                    "passed": gate.passed,
                    "actual": gate.actual,
                    "required": gate.required,
                }
                for gate in self.setup_gates
            ],
            "trade_setup_action": self.trade_setup_action,
            "signal_score": self.signal_score,
            "signal_strength": self.signal_strength,
            "signal_entry_quality": self.signal_entry_quality,
            "signal_breakdown": dict(self.signal_breakdown),
            "risk_status": self.risk_status,
            "risk_gate": self.risk_gate,
            "risk_confidence": self.risk_confidence,
            "market_context": self.market_context.to_dict() if self.market_context else None,
        }


@dataclass(frozen=True)
class SwingBacktestDailyEquity:
    """Daily portfolio equity point."""

    date: date
    equity: Decimal
    cash: Decimal
    open_positions: int

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "equity": str(self.equity),
            "cash": str(self.cash),
            "open_positions": self.open_positions,
        }


@dataclass(frozen=True)
class SwingBacktestRegimeStat:
    """Trade performance grouped by entry-date market regime."""

    regime: str
    count: int
    avg_return_pct: float | None
    win_rate_pct: float | None
    total_pnl: Decimal

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "count": self.count,
            "avg_return_pct": self.avg_return_pct,
            "win_rate_pct": self.win_rate_pct,
            "total_pnl": str(self.total_pnl),
        }


@dataclass(frozen=True)
class SwingBacktestResponse:
    """Portfolio-level walk-forward result."""

    setup: str
    start_date: date
    end_date: date
    initial_capital: Decimal
    cost_bps: Decimal
    final_equity: Decimal
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    win_rate_pct: float | None
    avg_trade_return_pct: float | None
    profit_factor: float | None
    exposure_pct: float
    skipped_no_cash: int
    skipped_duplicate: int
    skipped_no_forward_data: int
    skipped_by_regime: int
    trades: list[SwingBacktestTrade] = field(default_factory=list)
    equity_curve: list[SwingBacktestDailyEquity] = field(default_factory=list)
    regime_stats: list[SwingBacktestRegimeStat] = field(default_factory=list)
    regime_by_date: dict[date, MarketContext] = field(default_factory=dict)
    attribution_summary: SwingBacktestAttributionSummary = field(
        default_factory=SwingBacktestAttributionSummary
    )
    warnings: list[str] = field(default_factory=list)


@dataclass
class _OpenPosition:
    ticker: str
    entry_date: date
    entry_price: Decimal
    lots: int
    shares: int
    entry_value: Decimal
    entry_cost: Decimal
    foreign_flow_score: float
    flow_pct: float | None
    vwap_disc_pct: float | None
    rsi: float | None
    regime: str | None
    setup_match: str | None
    setup_failed_reasons: tuple[str, ...]
    setup_gates: tuple[SetupGate, ...]
    trade_setup_action: str | None
    signal_score: int | None
    signal_strength: str | None
    signal_entry_quality: str | None
    signal_breakdown: tuple[tuple[str, float], ...]
    risk_status: str | None
    risk_gate: str | None
    risk_confidence: int | None
    market_context: MarketContext | None


@dataclass(frozen=True)
class _EntrySignal:
    candidate: AccumulationCandidate
    setup_evaluation: SetupEvaluation


class SwingBacktestUseCase:
    """
    Simulate the actual daily swing workflow with portfolio constraints.

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
    ) -> None:
        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._derived_features = derived_feature_policy or AccumulationDerivedFeaturePolicy()
        self._risk_engine = risk_engine
        self._screen = AccumulationScreenUseCase(
            broker_repository=broker_repository,
            market_repository=market_repository,
            derived_feature_policy=self._derived_features,
        )
        self._regime = MarketContextEngine(
            market_repository=market_repository,
            broker_repository=broker_repository,
        )

    def execute(self, request: SwingBacktestRequest) -> SwingBacktestResponse:
        self._validate(request)
        tickers = [ticker.upper().strip() for ticker in request.tickers if ticker.strip()]
        replay_dates = self._replay_dates(tickers, request.start_date, request.end_date)
        regime_by_date = self._regime_by_date(tickers, replay_dates, request)

        cash = request.capital
        open_positions: list[_OpenPosition] = []
        trades: list[SwingBacktestTrade] = []
        equity_curve: list[SwingBacktestDailyEquity] = []
        skipped_no_cash = 0
        skipped_duplicate = 0
        skipped_no_forward_data = 0
        skipped_by_regime = 0
        exposure_days = 0

        for current_date in replay_dates:
            closed_today: list[_OpenPosition] = []
            for position in list(open_positions):
                exit_trade = self._maybe_exit(position, current_date, request)
                if exit_trade is None:
                    continue
                cash += exit_trade.exit_value - self._trade_cost(exit_trade.exit_value, request)
                trades.append(exit_trade)
                closed_today.append(position)

            if closed_today:
                open_positions = [
                    p for p in open_positions
                    if not any(
                        p.ticker == closed.ticker and p.entry_date == closed.entry_date
                        for closed in closed_today
                    )
                ]

            available_slots = request.max_positions - len(open_positions)
            if available_slots > 0:
                candidates = self._signals_for_date(tickers, current_date, request)
                open_tickers = {p.ticker for p in open_positions}
                for entry_signal in candidates:
                    candidate = entry_signal.candidate
                    if available_slots <= 0:
                        break
                    if candidate.ticker in open_tickers:
                        skipped_duplicate += 1
                        continue
                    regime = regime_by_date.get(current_date)
                    regime_label = regime.regime.value if regime is not None else None
                    if not self._passes_regime_filter(regime_label, request):
                        skipped_by_regime += 1
                        continue
                    if not self._has_forward_data(candidate.ticker, current_date, request):
                        skipped_no_forward_data += 1
                        continue

                    position = self._build_position(
                        candidate,
                        entry_signal.setup_evaluation,
                        current_date,
                        cash,
                        request,
                        regime,
                    )
                    if position is None:
                        skipped_no_cash += 1
                        continue

                    cash -= position.entry_value + position.entry_cost
                    open_positions.append(position)
                    open_tickers.add(candidate.ticker)
                    available_slots -= 1

            equity = cash + self._mark_to_market(open_positions, current_date)
            if open_positions:
                exposure_days += 1
            equity_curve.append(SwingBacktestDailyEquity(
                date=current_date,
                equity=equity,
                cash=cash,
                open_positions=len(open_positions),
            ))

        if replay_dates:
            final_date = replay_dates[-1]
            for position in list(open_positions):
                exit_trade = self._force_exit(position, final_date, request)
                if exit_trade is None:
                    continue
                cash += exit_trade.exit_value - self._trade_cost(exit_trade.exit_value, request)
                trades.append(exit_trade)
            final_equity = cash
        else:
            final_equity = request.capital

        return SwingBacktestResponse(
            setup=request.setup,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.capital,
            cost_bps=request.cost_bps,
            final_equity=final_equity,
            total_return_pct=_pct_change(final_equity, request.capital),
            max_drawdown_pct=self._max_drawdown(equity_curve),
            trade_count=len(trades),
            win_rate_pct=_win_rate([float(t.pnl) for t in trades]),
            avg_trade_return_pct=_avg([t.net_return_pct for t in trades]),
            profit_factor=_profit_factor(trades),
            exposure_pct=round(exposure_days / len(replay_dates) * 100, 2)
            if replay_dates else 0.0,
            skipped_no_cash=skipped_no_cash,
            skipped_duplicate=skipped_duplicate,
            skipped_no_forward_data=skipped_no_forward_data,
            skipped_by_regime=skipped_by_regime,
            trades=trades,
            equity_curve=equity_curve,
            regime_stats=self._regime_stats(trades),
            regime_by_date=regime_by_date,
            attribution_summary=summarize_swing_backtest_attribution(
                trades,
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
    ) -> list[_EntrySignal]:
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
            if setup_evaluation.passed:
                candidates.append(_EntrySignal(candidate, setup_evaluation))
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

    def _passes_regime_filter(
        self,
        regime_label: str | None,
        request: SwingBacktestRequest,
    ) -> bool:
        if not request.allowed_regimes:
            return True
        if regime_label is None:
            return False
        allowed = {regime.upper() for regime in request.allowed_regimes}
        return regime_label.upper() in allowed

    def _build_position(
        self,
        candidate: AccumulationCandidate,
        setup_evaluation: SetupEvaluation,
        signal_date: date,
        cash: Decimal,
        request: SwingBacktestRequest,
        market_context: MarketContext | None,
    ) -> _OpenPosition | None:
        entry = candidate.current_price
        if entry <= 0:
            return None

        stop_distance = entry * request.stop_loss_pct / Decimal("100")
        if stop_distance <= 0:
            return None

        risk_amount = request.capital * request.risk_pct
        shares_by_risk = int(risk_amount / stop_distance)
        cost_multiplier = Decimal("1") + request.cost_bps / Decimal("10000")
        max_affordable_shares = int(cash / (entry * cost_multiplier))
        shares = min(shares_by_risk, max_affordable_shares)
        lots = shares // SHARES_PER_LOT
        shares = lots * SHARES_PER_LOT
        if lots <= 0:
            return None

        entry_value = Decimal(shares) * entry
        signal = candidate.signal_assessment.assessment if candidate.signal_assessment else None
        risk_response, trade_setup = self._assess_trade_setup(
            candidate=candidate,
            signal_date=signal_date,
            market_context=market_context,
        )
        risk = risk_response.assessment if risk_response is not None else None
        return _OpenPosition(
            ticker=candidate.ticker,
            entry_date=signal_date,
            entry_price=entry,
            lots=lots,
            shares=shares,
            entry_value=entry_value,
            entry_cost=self._trade_cost(entry_value, request),
            foreign_flow_score=candidate.foreign_flow_score,
            flow_pct=candidate.avg_flow_ratio,
            vwap_disc_pct=candidate.vwap_discount_pct,
            rsi=candidate.rsi,
            regime=market_context.regime.value if market_context is not None else None,
            setup_match=getattr(setup_evaluation.match, "value", str(setup_evaluation.match)),
            setup_failed_reasons=tuple(setup_evaluation.failed_reasons),
            setup_gates=setup_evaluation.gates,
            trade_setup_action=trade_setup.action.value if trade_setup is not None else None,
            signal_score=signal.score if signal is not None else None,
            signal_strength=signal.strength.value if signal is not None else None,
            signal_entry_quality=signal.entry_quality.value if signal is not None else None,
            signal_breakdown=signal.breakdown if signal is not None else (),
            risk_status=risk.risk_level_name if risk is not None else None,
            risk_gate=risk.gate_triggered if risk is not None else None,
            risk_confidence=risk.confidence if risk is not None else None,
            market_context=market_context,
        )

    def _assess_trade_setup(
        self,
        *,
        candidate: AccumulationCandidate,
        signal_date: date,
        market_context: MarketContext | None,
    ):
        if self._risk_engine is None or candidate.signal_assessment is None:
            return None, None

        try:
            risk_response = self._risk_engine.assess_with_context(
                candidate.ticker,
                self._build_gate_context(candidate, signal_date),
                market_context=market_context,
            )
        except Exception as exc:
            logger.debug(
                "Swing backtest risk attribution failed for %s on %s: %s",
                candidate.ticker,
                signal_date,
                exc,
            )
            return None, None
        trade_setup = AssessTradeSetupUseCase().execute(
            AssessTradeSetupRequest(
                ticker=candidate.ticker,
                snapshot_date=signal_date,
                signal_response=candidate.signal_assessment,
                risk_response=risk_response,
                market_context=market_context,
            )
        ).setup
        return risk_response, trade_setup

    @staticmethod
    def _build_gate_context(
        candidate: AccumulationCandidate,
        signal_date: date,
    ) -> GateContext:
        return GateContext(
            ticker=candidate.ticker,
            snapshot_date=signal_date,
            piotroski_f_score=(
                candidate.fundamentals.piotroski_f_score
                if candidate.fundamentals else None
            ),
            market_cap_idr=(
                candidate.fundamentals.market_cap_idr
                if candidate.fundamentals else None
            ),
            free_float_pct=(
                candidate.shareholding.free_float_pct
                if candidate.shareholding is not None else None
            ),
            five_day_accdist=(
                candidate.bandar_detector.five_day_accdist
                if candidate.bandar_detector else None
            ),
        )

    def _maybe_exit(
        self,
        position: _OpenPosition,
        current_date: date,
        request: SwingBacktestRequest,
    ) -> SwingBacktestTrade | None:
        if current_date <= position.entry_date:
            return None

        candle = self._candle_on(position.ticker, current_date)
        if candle is None:
            return None

        tp_pct = request.take_profit_pct
        sl_pct = request.stop_loss_pct
        if request.setup_targets:
            from src.application.use_case.accumulation_screen_use_case import resolve_setup_targets
            tp_pct, sl_pct = resolve_setup_targets(position.regime, {"setup_targets": request.setup_targets})

        target = position.entry_price * (
            Decimal("1") + tp_pct / Decimal("100")
        )
        stop = position.entry_price * (
            Decimal("1") - sl_pct / Decimal("100")
        )
        holding_days = self._holding_days(position.ticker, position.entry_date, current_date)

        stop_hit = candle.low <= stop
        target_hit = candle.high >= target
        if stop_hit and (
            request.same_day_exit_priority == "stop_first" or not target_hit
        ):
            return self._close_trade(position, current_date, stop, "stop", request)
        if target_hit:
            return self._close_trade(position, current_date, target, "target", request)
        if stop_hit:
            return self._close_trade(position, current_date, stop, "stop", request)
        if holding_days >= request.max_hold_days:
            return self._close_trade(position, current_date, candle.close, "max_hold", request)
        return None

    def _force_exit(
        self,
        position: _OpenPosition,
        exit_date: date,
        request: SwingBacktestRequest,
    ) -> SwingBacktestTrade | None:
        candle = self._candle_on(position.ticker, exit_date)
        if candle is None:
            return None
        return self._close_trade(position, exit_date, candle.close, "period_end", request)

    def _close_trade(
        self,
        position: _OpenPosition,
        exit_date: date,
        exit_price: Decimal,
        reason: str,
        request: SwingBacktestRequest,
    ) -> SwingBacktestTrade:
        exit_value = Decimal(position.shares) * exit_price
        exit_cost = self._trade_cost(exit_value, request)
        pnl = exit_value - exit_cost - position.entry_value - position.entry_cost
        gross_return = _pct_change(exit_price, position.entry_price)
        net_return = round(float(pnl / position.entry_value * Decimal("100")), 4)
        return SwingBacktestTrade(
            ticker=position.ticker,
            entry_date=position.entry_date,
            exit_date=exit_date,
            entry_price=position.entry_price,
            exit_price=exit_price,
            lots=position.lots,
            shares=position.shares,
            entry_value=position.entry_value,
            exit_value=exit_value,
            gross_return_pct=gross_return,
            net_return_pct=net_return,
            pnl=pnl,
            holding_days=self._holding_days(position.ticker, position.entry_date, exit_date),
            exit_reason=reason,
            foreign_flow_score=position.foreign_flow_score,
            flow_pct=position.flow_pct,
            vwap_disc_pct=position.vwap_disc_pct,
            rsi=position.rsi,
            regime=position.regime,
            setup_match=position.setup_match,
            setup_failed_reasons=position.setup_failed_reasons,
            setup_gates=position.setup_gates,
            trade_setup_action=position.trade_setup_action,
            signal_score=position.signal_score,
            signal_strength=position.signal_strength,
            signal_entry_quality=position.signal_entry_quality,
            signal_breakdown=position.signal_breakdown,
            risk_status=position.risk_status,
            risk_gate=position.risk_gate,
            risk_confidence=position.risk_confidence,
            market_context=position.market_context,
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

        engine = MarketContextEngine(
            market_repository=self._market_repo,
            universe=tickers,
            broker_repository=self._broker_repo,
        )
        regimes: dict[date, MarketContext] = {}
        for replay_date in replay_dates:
            regimes[replay_date] = engine.evaluate(as_of_date=replay_date)
        return regimes

    def _has_forward_data(
        self,
        ticker: str,
        signal_date: date,
        request: SwingBacktestRequest,
    ) -> bool:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=signal_date + timedelta(days=1),
            end_date=signal_date + timedelta(days=request.forward_data_lookahead_days),
        )
        return any(c.date > signal_date for c in candles)

    def _candle_on(self, ticker: str, target_date: date) -> Candle | None:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=target_date,
            end_date=target_date,
        )
        return candles[0] if candles else None

    def _holding_days(self, ticker: str, entry_date: date, exit_date: date) -> int:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=entry_date + timedelta(days=1),
            end_date=exit_date,
        )
        return len([c for c in candles if entry_date < c.date <= exit_date])

    def _mark_to_market(
        self,
        positions: list[_OpenPosition],
        current_date: date,
    ) -> Decimal:
        value = Decimal("0")
        for position in positions:
            candle = self._candle_on(position.ticker, current_date)
            mark = candle.close if candle is not None else position.entry_price
            value += Decimal(position.shares) * mark
        return value

    def _trade_cost(self, value: Decimal, request: SwingBacktestRequest) -> Decimal:
        return value * request.cost_bps / Decimal("10000")

    def _max_drawdown(self, curve: list[SwingBacktestDailyEquity]) -> float:
        return max_drawdown_pct((point.equity for point in curve), precision=4)

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
                avg_return_pct=_avg([trade.net_return_pct for trade in rows]),
                win_rate_pct=_win_rate([float(trade.pnl) for trade in rows]),
                total_pnl=sum((trade.pnl for trade in rows), Decimal("0")),
            )
            for regime, rows in buckets.items()
        ]
        return sorted(stats, key=lambda s: s.count, reverse=True)


def _pct_change(value: Decimal, base: Decimal) -> float:
    return pct_change(value, base, precision=4)


def _avg(values: list[float]) -> float | None:
    return average(values, precision=4)


def _win_rate(values: list[float]) -> float | None:
    return win_rate(values, precision=2)


def _profit_factor(trades: list[SwingBacktestTrade]) -> float | None:
    return profit_factor((trade.pnl for trade in trades), precision=4)
