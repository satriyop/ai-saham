"""
Walk-forward portfolio backtest for deterministic swing trade presets.

Layer: Application
Depends on: Domain ports and accumulation screen use case
AI usage: None
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean

from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
)
from src.application.use_case.market_regime import (
    MarketRegimeRequest,
    MarketRegimeResponse,
    MarketRegimeUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository

SHARES_PER_LOT = 100
FOREIGN_BOUNCE_PRESET = "foreign-bounce"
DEFAULT_SWING_COST_BPS = Decimal("20")


@dataclass(frozen=True)
class SwingBacktestRequest:
    """Input parameters for a walk-forward swing workflow backtest."""

    tickers: list[str]
    start_date: date
    end_date: date
    preset: str = FOREIGN_BOUNCE_PRESET
    capital: Decimal = Decimal("100000000")
    risk_pct: Decimal = Decimal("0.01")
    max_positions: int = 5
    window_days: int = 7
    min_net_buy_days: int = 2
    min_score: float = 70.0
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
    score: float
    flow_pct: float | None
    vwap_disc_pct: float | None
    rsi: float | None
    regime: str | None = None

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
            "score": self.score,
            "flow_pct": self.flow_pct,
            "vwap_disc_pct": self.vwap_disc_pct,
            "rsi": self.rsi,
            "regime": self.regime,
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

    preset: str
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
    regime_by_date: dict[date, MarketRegimeResponse] = field(default_factory=dict)
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
    score: float
    flow_pct: float | None
    vwap_disc_pct: float | None
    rsi: float | None
    regime: str | None


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
    ) -> None:
        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._screen = AccumulationScreenUseCase(
            broker_repository=broker_repository,
            market_repository=market_repository,
        )
        self._regime = MarketRegimeUseCase(
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
                for candidate in candidates:
                    if available_slots <= 0:
                        break
                    if candidate.ticker in open_tickers:
                        skipped_duplicate += 1
                        continue
                    regime = regime_by_date.get(current_date)
                    regime_label = regime.label if regime is not None else None
                    if not self._passes_regime_filter(regime_label, request):
                        skipped_by_regime += 1
                        continue
                    if not self._has_forward_data(candidate.ticker, current_date):
                        skipped_no_forward_data += 1
                        continue

                    position = self._build_position(
                        candidate,
                        current_date,
                        cash,
                        request,
                        regime_label,
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
            preset=request.preset,
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
            warnings=[
                "Backtest uses the supplied current universe; "
                "historical index membership is not reconstructed.",
                "Signals enter at same-day close; intraday execution/slippage is not modeled.",
            ],
        )

    def _validate(self, request: SwingBacktestRequest) -> None:
        if request.preset != FOREIGN_BOUNCE_PRESET:
            raise ValueError(f"Unsupported swing preset: {request.preset}")
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
        valid_regimes = {"BULLISH", "SIDEWAYS", "WEAK", "RISK_OFF"}
        invalid = [r for r in request.allowed_regimes if r.upper() not in valid_regimes]
        if invalid:
            raise ValueError(
                "allowed_regimes must contain only: BULLISH, SIDEWAYS, WEAK, RISK_OFF"
            )

    def _signals_for_date(
        self,
        tickers: list[str],
        signal_date: date,
        request: SwingBacktestRequest,
    ) -> list[AccumulationCandidate]:
        response = self._screen.execute(AccumulationScreenRequest(
            tickers=tickers,
            window_days=request.window_days,
            min_net_buy_days=request.min_net_buy_days,
            min_score=request.min_score,
            as_of_date=signal_date,
        ))
        candidates = [
            candidate for candidate in response.candidates
            if self._passes_preset(candidate, request)
        ]
        return sorted(
            candidates,
            key=lambda c: (
                c.score,
                c.avg_flow_ratio or 0.0,
                c.vwap_discount_pct or 0.0,
            ),
            reverse=True,
        )

    def _passes_preset(
        self,
        candidate: AccumulationCandidate,
        request: SwingBacktestRequest,
    ) -> bool:
        return (
            candidate.score >= request.min_score
            and candidate.vwap_discount_pct is not None
            and candidate.vwap_discount_pct >= request.min_vwap_disc_pct
            and candidate.trend.upper() == request.trend.upper()
            and candidate.avg_flow_ratio is not None
            and candidate.avg_flow_ratio >= request.min_flow_pct
            and candidate.rsi is not None
            and candidate.rsi <= request.max_rsi
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
        signal_date: date,
        cash: Decimal,
        request: SwingBacktestRequest,
        regime: str | None,
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
        return _OpenPosition(
            ticker=candidate.ticker,
            entry_date=signal_date,
            entry_price=entry,
            lots=lots,
            shares=shares,
            entry_value=entry_value,
            entry_cost=self._trade_cost(entry_value, request),
            score=candidate.score,
            flow_pct=candidate.avg_flow_ratio,
            vwap_disc_pct=candidate.vwap_discount_pct,
            rsi=candidate.rsi,
            regime=regime,
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

        target = position.entry_price * (
            Decimal("1") + request.take_profit_pct / Decimal("100")
        )
        stop = position.entry_price * (
            Decimal("1") - request.stop_loss_pct / Decimal("100")
        )
        holding_days = self._holding_days(position.ticker, position.entry_date, current_date)

        if candle.low <= stop:
            return self._close_trade(position, current_date, stop, "stop", request)
        if candle.high >= target:
            return self._close_trade(position, current_date, target, "target", request)
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
            score=position.score,
            flow_pct=position.flow_pct,
            vwap_disc_pct=position.vwap_disc_pct,
            rsi=position.rsi,
            regime=position.regime,
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
    ) -> dict[date, MarketRegimeResponse]:
        if not request.include_regime and not request.allowed_regimes:
            return {}

        regimes: dict[date, MarketRegimeResponse] = {}
        for replay_date in replay_dates:
            regimes[replay_date] = self._regime.execute(MarketRegimeRequest(
                universe=tickers,
                benchmark_ticker=request.benchmark_ticker,
                as_of_date=replay_date,
            ))
        return regimes

    def _has_forward_data(self, ticker: str, signal_date: date) -> bool:
        candles = self._market_repo.get_candles(
            ticker,
            start_date=signal_date + timedelta(days=1),
            end_date=signal_date + timedelta(days=45),
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
        peak: Decimal | None = None
        max_dd = Decimal("0")
        for point in curve:
            if peak is None or point.equity > peak:
                peak = point.equity
            if peak and peak > 0:
                drawdown = (point.equity - peak) / peak * Decimal("100")
                if drawdown < max_dd:
                    max_dd = drawdown
        return round(float(max_dd), 4)

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
    if base == 0:
        return 0.0
    return round(float((value - base) / base * Decimal("100")), 4)


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _win_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value > 0) / len(values) * 100, 2)


def _profit_factor(trades: list[SwingBacktestTrade]) -> float | None:
    gains = sum((trade.pnl for trade in trades if trade.pnl > 0), Decimal("0"))
    losses = abs(sum((trade.pnl for trade in trades if trade.pnl < 0), Decimal("0")))
    if losses == 0:
        return None if gains == 0 else float("inf")
    return round(float(gains / losses), 4)
