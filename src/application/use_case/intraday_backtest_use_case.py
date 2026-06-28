"""
Daily-OHLC proxy simulation for the deterministic intraday pre-open workflow.

Uses daily OHLC as a proxy for intraday execution (Option A):
  - Screening reuses pre-open math (ATR/RSI/SMA, entry range, ATR stop, ACCUM, FVWAP).
    IEV filter is intentionally OMITTED — historical IEV is not stored.
  - Opening price proxy = candle.open (IDX 09:00 call-auction clearing price).
  - Same-day exit only. No overnight holds.
  - Stop check uses candle.low; target check uses candle.high (prev_high).
  - Conservative H/L ordering: if both stop and target are breached on the same day,
    assume stop hit first.
  - Fallback exit: candle.close at session end.

Layer: Application
Depends on: ConfirmIntradayOpenUseCase, IndicatorRegistry, market+broker repositories
AI usage: None
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.stats import (
    average,
    foreign_vwap_discount_pct,
    max_drawdown_pct,
    profit_factor,
)
from src.application.use_case.confirm_intraday_open_use_case import (
    ConfirmIntradayOpenRequest,
    ConfirmIntradayOpenUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.idx_market import SHARES_PER_LOT
from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmationCandidate,
    IntradayDecision,
)

PER_TRADE_CAPITAL_CAP_PCT = Decimal("0.10")  # at most 10% of capital per trade


# ── Request ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntradayBacktestRequest:
    """Input parameters for a daily-OHLC intraday proxy simulation."""

    tickers: list[str]
    start_date: date
    end_date: date
    capital: Decimal = Decimal("100000000")
    risk_pct: Decimal = Decimal("0.01")           # 1% of capital at risk per trade
    max_daily_positions: int = 3
    atr_period: int = 14
    rsi_period: int = 14
    sma_period: int = 20
    atr_multiplier: Decimal = Decimal("1.0")
    max_stop_pct: Decimal = Decimal("0.07")        # 7% max stop distance
    rsi_overbought_threshold: Decimal = Decimal("75")
    atr_range_cap_min: Decimal = Decimal("0.01")   # 1% floor on ATR band
    atr_range_cap_max: Decimal = Decimal("0.05")   # 5% ceiling on ATR band
    accum_window_days: int = 7
    accum_backed_threshold: float = 50.0
    fvwap_period: int = 20
    history_days: int = 60                         # min candle lookback per ticker
    include_wait: bool = False                     # treat WAIT as ENTER if True
    cost_bps: Decimal = Decimal("20")              # bps per side (round-trip = 2×)
    iev_top_n: int = 5                             # when IEV data available, keep only top-N movers


# ── Result DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntradayBacktestTrade:
    """One completed intraday proxy trade (same-day in + out)."""

    ticker: str
    trade_date: date
    decision: str                    # "ENTER" or "WAIT" (when include_wait)
    opening_price: Decimal
    entry_price: Decimal
    exit_price: Decimal
    exit_reason: str                 # "target" | "stop" | "close" | "both_assume_stop"
    stop_price: Decimal
    target_price: Decimal
    lots: int
    shares: int
    entry_value: Decimal
    exit_value: Decimal
    cost_total: Decimal
    gross_return_pct: float
    net_return_pct: float
    pnl: Decimal
    r_multiple: float | None
    # screener diagnostics
    trend: str | None
    rsi: float | None
    atr: float | None
    accum_tag: str | None
    broker_accum_score: float | None
    accum_streak: int | None
    fvwap_discount_pct: float | None
    prev_high: Decimal | None
    entry_range_low: Decimal | None
    entry_range_high: Decimal | None
    same_day_both_breached: bool

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "trade_date": self.trade_date.isoformat(),
            "decision": self.decision,
            "opening_price": str(self.opening_price),
            "entry_price": str(self.entry_price),
            "exit_price": str(self.exit_price),
            "exit_reason": self.exit_reason,
            "stop_price": str(self.stop_price),
            "target_price": str(self.target_price),
            "lots": self.lots,
            "shares": self.shares,
            "entry_value": str(self.entry_value),
            "exit_value": str(self.exit_value),
            "cost_total": str(self.cost_total),
            "gross_return_pct": self.gross_return_pct,
            "net_return_pct": self.net_return_pct,
            "pnl": str(self.pnl),
            "r_multiple": self.r_multiple,
            "trend": self.trend,
            "rsi": self.rsi,
            "atr": self.atr,
            "accum_tag": self.accum_tag,
            "broker_accum_score": self.broker_accum_score,
            "accum_streak": self.accum_streak,
            "fvwap_discount_pct": self.fvwap_discount_pct,
            "prev_high": str(self.prev_high) if self.prev_high is not None else None,
            "entry_range_low": str(self.entry_range_low) if self.entry_range_low is not None else None,
            "entry_range_high": str(self.entry_range_high) if self.entry_range_high is not None else None,
            "same_day_both_breached": self.same_day_both_breached,
        }


@dataclass(frozen=True)
class IntradayBacktestResponse:
    """Aggregate result of a daily-OHLC intraday proxy simulation."""

    # Config echo
    start_date: date
    end_date: date
    initial_capital: Decimal
    cost_bps: Decimal
    include_wait: bool
    max_daily_positions: int

    # Equity
    final_equity: Decimal
    total_return_pct: float
    max_drawdown_pct: float

    # Trade stats
    trade_count: int
    win_rate_pct: float | None
    avg_trade_return_pct: float | None
    avg_winner_pct: float | None
    avg_loser_pct: float | None
    profit_factor: float | None
    expectancy_pct: float | None
    avg_r_multiple: float | None
    exit_reason_counts: dict[str, int]
    decisions: dict[str, int]

    # Days
    trading_days: int
    days_with_trades: int

    # Signal-quality breakdowns
    by_accum_tag: list[dict]
    by_fvwap_sign: list[dict]
    by_rsi_bucket: list[dict]
    by_ticker: list[dict]

    trades: list[IntradayBacktestTrade] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Internal helpers ───────────────────────────────────────────────────────────


@dataclass
class _BacktestCandidate:
    """Intermediate object carrying pre-open signals for one ticker on signal_date."""

    ticker: str
    prev_close: Decimal
    prev_high: Decimal | None
    prev_low: Decimal | None
    atr: Decimal | None
    rsi: Decimal | None
    sma: Decimal | None
    entry_range_low: Decimal | None
    entry_range_high: Decimal | None
    atr_stop: Decimal | None
    trend: str | None
    broker_accum_score: float | None
    accum_tag: str | None
    accum_streak: int | None
    fvwap_discount_pct: float | None


def _compute_entry_range(
    prev_close: Decimal,
    atr: Decimal | None,
    cap_min: Decimal,
    cap_max: Decimal,
) -> tuple[Decimal, Decimal | None, Decimal | None]:
    """Compute ATR-scaled entry range. Returns (effective_band, range_low, range_high)."""
    if atr is not None and prev_close > 0:
        atr_pct = atr / prev_close
        effective_band = max(cap_min, min(atr_pct, cap_max))
    else:
        effective_band = cap_max

    if prev_close <= 0:
        return effective_band, None, None

    low = (prev_close * (1 - effective_band)).quantize(Decimal("1"))
    high = (prev_close * (1 + effective_band)).quantize(Decimal("1"))
    return effective_band, low, high


def _classify_trend_backtest(
    rsi: Decimal | None,
    sma: Decimal | None,
    close: Decimal | None,
    overbought: Decimal,
) -> str | None:
    """Trend classifier for backtest context (no gap% available, uses SMA fallback)."""
    if rsi is None:
        return None
    if rsi > overbought:
        return "BEARISH"
    if close is not None and sma is not None:
        above_sma = close > sma
        if Decimal("30") < rsi < Decimal("65") and above_sma:
            return "BULLISH"
        if not above_sma and rsi > Decimal("65"):
            return "BEARISH"
        if above_sma and rsi < Decimal("40"):
            return "DIP_BUY"
    elif Decimal("30") < rsi < Decimal("65"):
        return "BULLISH"
    return "NEUTRAL"


def _assess_broker_as_of(
    ticker: str,
    broker_repo: BrokerDataRepository,
    candles: list[Candle],
    current_price: Decimal | None,
    signal_date: date,
    accum_window: int,
    accum_threshold: float,
    fvwap_period: int,
) -> dict:
    """Compute ACCUM tag + Foreign VWAP using data available as of signal_date.

    Critical: uses signal_date (not date.today()) to avoid lookahead bias.
    """
    empty: dict = {
        "broker_accum_score": None, "accum_tag": None, "accum_streak": None,
        "fvwap_discount_pct": None,
    }
    try:
        start = signal_date - timedelta(days=accum_window + fvwap_period + 10)
        summaries = broker_repo.get_broker_summaries(
            ticker=ticker, start_date=start, end_date=signal_date,
        )
    except Exception:
        return empty

    if not summaries:
        return empty

    result = dict(empty)

    cutoff = signal_date - timedelta(days=accum_window)
    window = [s for s in summaries if s.date > cutoff]

    if window:
        net_buy_days = sum(1 for s in window if s.is_foreign_accumulating)
        total_days = len(window)
        ratio = net_buy_days / total_days if total_days > 0 else 0.0

        streak = 0
        for s in sorted(window, key=lambda x: x.date, reverse=True):
            if s.is_foreign_accumulating:
                streak += 1
            else:
                break

        score = round(ratio * 40.0 + 30.0 * (1.0 - math.exp(-streak / 7.0)), 1)

        if score >= accum_threshold:
            tag = "BACKED"
        elif ratio < 0.3:
            tag = "DISTRIBUTING"
        else:
            tag = "UNCONFIRMED"

        result["broker_accum_score"] = score
        result["accum_tag"] = tag
        result["accum_streak"] = streak

    if candles and current_price is not None and current_price > 0:
        try:
            from plugins.indicators.foreign_vwap import ForeignVWAPIndicator  # type: ignore[import]
            indicator = ForeignVWAPIndicator()
            indicator.set_broker_data(summaries)
            vwap_values = indicator.compute(
                candles[-max(len(candles), fvwap_period):], fvwap_period,
            )
            if vwap_values:
                fvwap = vwap_values[-1]
                if fvwap > 0:
                    result["fvwap_discount_pct"] = foreign_vwap_discount_pct(
                        fvwap,
                        current_price,
                        precision=2,
                    )
        except Exception:
            pass

    return result


def _size_position(
    entry: Decimal,
    stop: Decimal,
    capital: Decimal,
    risk_pct: Decimal,
    cash: Decimal,
    cost_bps: Decimal,
) -> tuple[int, int]:
    """Compute (lots, shares) respecting risk, capital cap, and cash."""
    stop_distance = entry - stop
    if stop_distance <= 0:
        return 0, 0

    risk_amount = capital * risk_pct
    shares_by_risk = int(risk_amount / stop_distance)

    per_trade_cap = capital * PER_TRADE_CAPITAL_CAP_PCT
    shares_by_cap = int(per_trade_cap / entry) if entry > 0 else 0

    cost_multiplier = Decimal("1") + cost_bps / Decimal("10000")
    shares_by_cash = int(cash / (entry * cost_multiplier)) if cash > 0 and entry > 0 else 0

    shares = min(shares_by_risk, shares_by_cap, shares_by_cash)
    lots = shares // SHARES_PER_LOT
    return lots, lots * SHARES_PER_LOT


def _compute_pnl(
    shares: int,
    entry: Decimal,
    exit_price: Decimal,
    cost_bps: Decimal,
) -> tuple[Decimal, float, float, Decimal]:
    """Return (pnl, gross_return_pct, net_return_pct, cost_total)."""
    entry_value = Decimal(shares) * entry
    exit_value = Decimal(shares) * exit_price
    entry_cost = entry_value * cost_bps / Decimal("10000")
    exit_cost = exit_value * cost_bps / Decimal("10000")
    cost_total = entry_cost + exit_cost
    pnl = exit_value - exit_cost - entry_value - entry_cost
    gross_pct = round(float((exit_price - entry) / entry * 100), 4) if entry > 0 else 0.0
    net_pct = round(float(pnl / entry_value * 100), 4) if entry_value > 0 else 0.0
    return pnl, gross_pct, net_pct, cost_total


def _max_drawdown(equity_curve: list[Decimal]) -> float:
    return max_drawdown_pct(equity_curve, precision=4)


def _avg(values: list[float]) -> float | None:
    return average(values, precision=4)


def _profit_factor(trades: list[IntradayBacktestTrade]) -> float | None:
    return profit_factor((trade.pnl for trade in trades), precision=3)


def _expectancy(trades: list[IntradayBacktestTrade]) -> float | None:
    if not trades:
        return None
    wins = [t.net_return_pct for t in trades if t.pnl > 0]
    losses = [t.net_return_pct for t in trades if t.pnl < 0]
    if not wins and not losses:
        return None
    win_rate = len(wins) / len(trades)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    return round(win_rate * avg_win + (1 - win_rate) * avg_loss, 4)


def _rsi_bucket(rsi: float | None) -> str:
    if rsi is None:
        return "rsi:missing"
    if rsi < 30:
        return "rsi:<30"
    if rsi <= 55:
        return "rsi:30-55"
    if rsi <= 70:
        return "rsi:55-70"
    return "rsi:>70"


def _breakdown_by(
    trades: list[IntradayBacktestTrade],
    key_fn,
    label_fn=None,
) -> list[dict]:
    """Generic breakdown: group trades by key, compute win_rate + avg_ret + total_pnl."""
    groups: dict[str, list[IntradayBacktestTrade]] = {}
    for t in trades:
        k = key_fn(t)
        groups.setdefault(k, []).append(t)

    rows = []
    for key, group in sorted(groups.items()):
        wins = [g for g in group if g.pnl > 0]
        rets = [g.net_return_pct for g in group]
        rows.append({
            "label": label_fn(key) if label_fn else key,
            "count": len(group),
            "win_rate_pct": round(len(wins) / len(group) * 100, 1) if group else None,
            "avg_return_pct": round(sum(rets) / len(rets), 4) if rets else None,
            "total_pnl": sum(g.pnl for g in group),
        })
    return rows


# ── Use case ───────────────────────────────────────────────────────────────────


class IntradayBacktestUseCase:
    """Walk-forward intraday proxy simulation using daily OHLC.

    For each trading date d in [start_date, end_date]:
      1. Build pre-open candidates as of d-1 (yesterday's data → today's plan)
      2. Simulate opening confirmation with opening_price = candle.open on d
      3. Rank and cap entries at max_daily_positions
      4. Simulate same-day exit via candle.high / candle.low / candle.close
      5. Update cash and equity; no overnight holds
    """

    def __init__(
        self,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        indicator_registry: IndicatorRegistry,
        iev_repository=None,   # SQLiteIEVRepository | None — optional for IEV filtering
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = indicator_registry
        self._iev_repo = iev_repository
        self._confirm = ConfirmIntradayOpenUseCase()

    def execute(self, request: IntradayBacktestRequest) -> IntradayBacktestResponse:
        self._validate(request)
        tickers = list(dict.fromkeys(t.upper().strip() for t in request.tickers))

        trading_dates = self._replay_dates(tickers, request.start_date, request.end_date)
        if not trading_dates:
            return self._empty_response(request, ["No trading dates with candle data in range."])

        cash = request.capital
        equity_curve: list[Decimal] = [cash]
        peak = cash
        max_dd = Decimal("0")
        all_trades: list[IntradayBacktestTrade] = []
        warnings: list[str] = []
        days_with_trades = 0

        for d in trading_dates:
            day_trades: list[IntradayBacktestTrade] = []
            daily_positions_opened = 0

            # ── Step 1: build pre-open candidates as of d-1 ──────────────────
            candidates: list[_BacktestCandidate] = []
            for ticker in tickers:
                c = self._build_candidate(ticker, d, request)
                if c is not None:
                    candidates.append(c)

            if not candidates:
                equity_curve.append(cash)
                continue

            # ── Step 1b: apply IEV filter when snapshot is available ──────────
            if self._iev_repo is not None and self._iev_repo.has_snapshot(d):
                snapshot = self._iev_repo.get_ncp_snapshot(d, top_n=request.iev_top_n)
                iev_tickers = {s.ticker for s in snapshot}
                candidates = [c for c in candidates if c.ticker in iev_tickers]
                if not candidates:
                    equity_curve.append(cash)
                    continue

            # ── Step 2: fetch today's candles + simulate opening confirmation ─
            conf_candidates = []
            candidate_map: dict[str, _BacktestCandidate] = {}
            today_candles: dict[str, Candle] = {}

            for cand in candidates:
                raw = self._market_repo.get_candles(cand.ticker, start_date=d, end_date=d)
                if not raw:
                    continue
                today_candle = raw[0]
                today_candles[cand.ticker] = today_candle
                candidate_map[cand.ticker] = cand
                conf_candidates.append(IntradayConfirmationCandidate(
                    ticker=cand.ticker,
                    opening_price=today_candle.open,
                    iev=None,
                    entry_range_low=cand.entry_range_low,
                    entry_range_high=cand.entry_range_high,
                    suggested_entry=cand.prev_close,
                    atr_stop=cand.atr_stop,
                    trend=cand.trend,
                    rsi=cand.rsi,
                    gap_pct=None,
                    accum_tag=cand.accum_tag,
                    fvwap_discount_pct=(
                        Decimal(str(cand.fvwap_discount_pct))
                        if cand.fvwap_discount_pct is not None else None
                    ),
                ))

            if not conf_candidates:
                equity_curve.append(cash)
                continue

            confirm_result = self._confirm.execute(ConfirmIntradayOpenRequest(
                candidates=conf_candidates,
                run_date=d,
                max_stop_pct=request.max_stop_pct,
                # Tick-friction and regime gates apply to forward trading only.
                # Backtests replay historical decisions without these forward-looking filters.
                tick_friction_gate=False,
                regime_gate_enabled=False,
            ))

            # ── Step 3: filter, rank, and cap ────────────────────────────────
            accepted_decisions = {IntradayDecision.ENTER}
            if request.include_wait:
                accepted_decisions.add(IntradayDecision.WAIT)

            entries = [
                conf for conf in confirm_result.confirmations
                if conf.decision in accepted_decisions
            ]

            def _rank_key(conf):
                cand = candidate_map.get(conf.ticker)
                broker_accum_score = cand.broker_accum_score if cand else None
                fvwap = cand.fvwap_discount_pct if cand else None
                stop_pct = float(conf.stop_pct) if conf.stop_pct else 999.0
                return (
                    -(broker_accum_score or 0.0),
                    -(fvwap or 0.0),
                    stop_pct,
                    conf.ticker,
                )

            entries.sort(key=_rank_key)
            entries = entries[:request.max_daily_positions]

            # ── Step 4: simulate each entry ───────────────────────────────────
            for conf in entries:
                cand = candidate_map[conf.ticker]
                today_candle = today_candles[conf.ticker]

                entry = today_candle.open
                stop = cand.atr_stop
                if stop is None:
                    stop = entry * (Decimal("1") - request.max_stop_pct)
                    stop = stop.quantize(Decimal("1"))

                # Target = prev_high (only if above entry); fallback = entry + ATR
                if cand.prev_high is not None and cand.prev_high > entry:
                    target = cand.prev_high
                elif cand.atr is not None:
                    target = (entry + cand.atr).quantize(Decimal("1"))
                else:
                    target = (entry * (Decimal("1") + request.max_stop_pct)).quantize(Decimal("1"))

                lots, shares = _size_position(
                    entry, stop, request.capital, request.risk_pct, cash, request.cost_bps,
                )
                if lots <= 0:
                    continue

                # Determine exit
                hit_stop = today_candle.low <= stop
                hit_target = today_candle.high >= target
                both_breached = hit_stop and hit_target

                if both_breached:
                    exit_price = stop
                    exit_reason = "both_assume_stop"
                elif hit_stop:
                    exit_price = stop
                    exit_reason = "stop"
                elif hit_target:
                    exit_price = target
                    exit_reason = "target"
                else:
                    exit_price = today_candle.close
                    exit_reason = "close"

                pnl, gross_pct, net_pct, cost_total = _compute_pnl(
                    shares, entry, exit_price, request.cost_bps,
                )
                entry_value = Decimal(shares) * entry
                exit_value = Decimal(shares) * exit_price

                stop_distance = entry - stop
                initial_risk = Decimal(shares) * stop_distance
                r_multiple = round(float(pnl / initial_risk), 3) if initial_risk > 0 else None

                # Update cash
                cash -= entry_value + (entry_value * request.cost_bps / Decimal("10000"))
                cash += exit_value - (exit_value * request.cost_bps / Decimal("10000"))

                trade = IntradayBacktestTrade(
                    ticker=conf.ticker,
                    trade_date=d,
                    decision=conf.decision.value,
                    opening_price=entry,
                    entry_price=entry,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    stop_price=stop,
                    target_price=target,
                    lots=lots,
                    shares=shares,
                    entry_value=entry_value,
                    exit_value=exit_value,
                    cost_total=cost_total,
                    gross_return_pct=gross_pct,
                    net_return_pct=net_pct,
                    pnl=pnl,
                    r_multiple=r_multiple,
                    trend=cand.trend,
                    rsi=float(cand.rsi) if cand.rsi is not None else None,
                    atr=float(cand.atr) if cand.atr is not None else None,
                    accum_tag=cand.accum_tag,
                    broker_accum_score=cand.broker_accum_score,
                    accum_streak=cand.accum_streak,
                    fvwap_discount_pct=cand.fvwap_discount_pct,
                    prev_high=cand.prev_high,
                    entry_range_low=cand.entry_range_low,
                    entry_range_high=cand.entry_range_high,
                    same_day_both_breached=both_breached,
                )
                day_trades.append(trade)
                daily_positions_opened += 1

            all_trades.extend(day_trades)
            if day_trades:
                days_with_trades += 1

            # ── Step 5: end-of-day equity (no overnight positions) ────────────
            equity = cash
            equity_curve.append(equity)
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (equity - peak) / peak * Decimal("100")
                if dd < max_dd:
                    max_dd = dd

        if self._iev_repo is not None:
            iev_dates = set(self._iev_repo.get_snapshot_dates())
            covered = len([d for d in trading_dates if d in iev_dates])
            warnings.append(
                f"IEV filter active: snapshot data covers {covered}/{len(trading_dates)} "
                f"trading days in this period (top-{request.iev_top_n} movers per day)."
            )
            if covered < len(trading_dates):
                missing = len(trading_dates) - covered
                warnings.append(
                    f"IEV filter NOT applied on {missing} days (no snapshot). "
                    "Full universe screened on those days — run collect-iev daily to close the gap."
                )
        else:
            warnings.append(
                "IEV filter NOT active — full universe screened every day. "
                "Run 'saham fetch iev' at 08:50 WIB each trading day to build history."
            )
        warnings.extend([
            "Same-day H/L ordering is conservative: "
            "both-breached cases assume stop hit first.",
            "Opening price = candle.open (IDX 09:00 call-auction clearing price proxy).",
            "Tick-friction and regime gates are NOT replayed in this daily-OHLC proxy.",
        ])
        if not request.include_wait:
            warnings.append("WAIT decisions are skipped by default; use --include-wait to include them.")

        both_count = sum(1 for t in all_trades if t.same_day_both_breached)
        if all_trades and both_count / len(all_trades) > 0.15:
            warnings.append(
                f"WARNING: {both_count}/{len(all_trades)} trades ({both_count / len(all_trades):.0%}) "
                "had same-day H/L ambiguity — daily OHLC proxy may be too coarse for this universe."
            )

        return self._build_response(
            request=request,
            trades=all_trades,
            final_equity=cash,
            equity_curve=equity_curve,
            trading_days=len(trading_dates),
            days_with_trades=days_with_trades,
            warnings=warnings,
        )

    # ── Candidate builder ──────────────────────────────────────────────────────

    def _build_candidate(
        self,
        ticker: str,
        trade_date: date,
        request: IntradayBacktestRequest,
    ) -> _BacktestCandidate | None:
        """Build pre-open signals for ticker using data strictly before trade_date."""
        lookback_start = trade_date - timedelta(days=request.history_days * 2)
        lookback_end = trade_date - timedelta(days=1)

        candles = self._market_repo.get_candles(
            ticker, start_date=lookback_start, end_date=lookback_end,
        )
        if not candles:
            return None

        # Slice to history_days
        if len(candles) > request.history_days:
            candles = candles[-request.history_days:]

        min_required = max(request.atr_period, request.rsi_period, request.sma_period) + 2
        if len(candles) < min_required:
            return None

        prev = candles[-1]
        signal_date = prev.date  # actual last data date (may differ from trade_date-1 on holidays)

        # Compute indicators
        atr_values = self._registry.compute("ATR", candles, request.atr_period)
        rsi_values = self._registry.compute("RSI", candles, request.rsi_period)
        sma_values = self._registry.compute("SMA", candles, request.sma_period)

        atr = atr_values[-1][1] if atr_values else None
        rsi = rsi_values[-1][1] if rsi_values else None
        sma = sma_values[-1][1] if sma_values else None

        # Entry range
        _, range_low, range_high = _compute_entry_range(
            prev.close, atr, request.atr_range_cap_min, request.atr_range_cap_max,
        )

        # ATR stop (anchored on prev.close)
        if atr is not None:
            raw_stop = prev.close - request.atr_multiplier * atr
            floor_stop = prev.close * (Decimal("1") - request.max_stop_pct)
            atr_stop = max(raw_stop, floor_stop).quantize(Decimal("1"))
        else:
            atr_stop = (prev.close * (Decimal("1") - request.max_stop_pct)).quantize(Decimal("1"))

        trend = _classify_trend_backtest(rsi, sma, prev.close, request.rsi_overbought_threshold)

        # Broker signals — use signal_date to avoid lookahead
        broker = _assess_broker_as_of(
            ticker=ticker,
            broker_repo=self._broker_repo,
            candles=candles,
            current_price=prev.close,
            signal_date=signal_date,
            accum_window=request.accum_window_days,
            accum_threshold=request.accum_backed_threshold,
            fvwap_period=request.fvwap_period,
        )

        return _BacktestCandidate(
            ticker=ticker,
            prev_close=prev.close,
            prev_high=prev.high,
            prev_low=prev.low,
            atr=atr,
            rsi=rsi,
            sma=sma,
            entry_range_low=range_low,
            entry_range_high=range_high,
            atr_stop=atr_stop,
            trend=trend,
            broker_accum_score=broker["broker_accum_score"],
            accum_tag=broker["accum_tag"],
            accum_streak=broker["accum_streak"],
            fvwap_discount_pct=broker["fvwap_discount_pct"],
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _replay_dates(self, tickers: list[str], start: date, end: date) -> list[date]:
        dates: set[date] = set()
        for ticker in tickers:
            candles = self._market_repo.get_candles(ticker, start_date=start, end_date=end)
            dates.update(c.date for c in candles)
        return sorted(dates)

    def _validate(self, request: IntradayBacktestRequest) -> None:
        if not request.tickers:
            raise ValueError("At least one ticker is required.")
        if request.start_date > request.end_date:
            raise ValueError("start_date must be <= end_date.")
        if request.capital <= 0:
            raise ValueError("capital must be positive.")
        if request.risk_pct <= 0:
            raise ValueError("risk_pct must be positive.")
        if request.max_daily_positions < 1:
            raise ValueError("max_daily_positions must be >= 1.")
        if request.max_stop_pct <= 0:
            raise ValueError("max_stop_pct must be positive.")
        if request.atr_range_cap_min > request.atr_range_cap_max:
            raise ValueError("atr_range_cap_min must be <= atr_range_cap_max.")

    def _build_response(
        self,
        request: IntradayBacktestRequest,
        trades: list[IntradayBacktestTrade],
        final_equity: Decimal,
        equity_curve: list[Decimal],
        trading_days: int,
        days_with_trades: int,
        warnings: list[str],
    ) -> IntradayBacktestResponse:
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]

        win_rate = round(len(wins) / len(trades) * 100, 1) if trades else None
        avg_ret = _avg([t.net_return_pct for t in trades])
        avg_win = _avg([t.net_return_pct for t in wins])
        avg_loss = _avg([t.net_return_pct for t in losses])
        pf = _profit_factor(trades)
        exp = _expectancy(trades)
        r_values = [t.r_multiple for t in trades if t.r_multiple is not None]
        avg_r = _avg(r_values) if r_values else None

        exit_counts: dict[str, int] = {}
        for t in trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        decision_counts: dict[str, int] = {}
        for t in trades:
            decision_counts[t.decision] = decision_counts.get(t.decision, 0) + 1

        total_return_pct = round(
            float((final_equity - request.capital) / request.capital * 100), 4,
        )

        by_accum = _breakdown_by(trades, lambda t: t.accum_tag or "none")
        by_fvwap = _breakdown_by(
            trades,
            lambda t: "positive" if (t.fvwap_discount_pct is not None and t.fvwap_discount_pct > 0) else "non-positive",
        )
        by_rsi = _breakdown_by(trades, lambda t: _rsi_bucket(t.rsi))
        by_ticker = _breakdown_by(trades, lambda t: t.ticker)
        by_ticker.sort(key=lambda r: -r["count"])
        by_ticker = by_ticker[:10]

        return IntradayBacktestResponse(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.capital,
            cost_bps=request.cost_bps,
            include_wait=request.include_wait,
            max_daily_positions=request.max_daily_positions,
            final_equity=final_equity,
            total_return_pct=total_return_pct,
            max_drawdown_pct=_max_drawdown(equity_curve),
            trade_count=len(trades),
            win_rate_pct=win_rate,
            avg_trade_return_pct=avg_ret,
            avg_winner_pct=avg_win,
            avg_loser_pct=avg_loss,
            profit_factor=pf,
            expectancy_pct=exp,
            avg_r_multiple=avg_r,
            exit_reason_counts=exit_counts,
            decisions=decision_counts,
            trading_days=trading_days,
            days_with_trades=days_with_trades,
            by_accum_tag=by_accum,
            by_fvwap_sign=by_fvwap,
            by_rsi_bucket=by_rsi,
            by_ticker=by_ticker,
            trades=trades,
            warnings=warnings,
        )

    def _empty_response(
        self,
        request: IntradayBacktestRequest,
        warnings: list[str],
    ) -> IntradayBacktestResponse:
        return IntradayBacktestResponse(
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.capital,
            cost_bps=request.cost_bps,
            include_wait=request.include_wait,
            max_daily_positions=request.max_daily_positions,
            final_equity=request.capital,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            trade_count=0,
            win_rate_pct=None,
            avg_trade_return_pct=None,
            avg_winner_pct=None,
            avg_loser_pct=None,
            profit_factor=None,
            expectancy_pct=None,
            avg_r_multiple=None,
            exit_reason_counts={},
            decisions={},
            trading_days=0,
            days_with_trades=0,
            by_accum_tag=[],
            by_fvwap_sign=[],
            by_rsi_bucket=[],
            by_ticker=[],
            trades=[],
            warnings=warnings,
        )
