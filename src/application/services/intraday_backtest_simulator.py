"""Simulation mechanics for daily-OHLC proxy intraday backtesting.

Runs the daily walk-forward logic, matching candidates with opening confirmations,
ranking entries, applying IEV filters, and evaluating daily exits.

Layer: Application Service
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.dto.intraday_backtest import IntradayBacktestRequest, IntradayBacktestTrade
from src.application.services.intraday_backtest_candidate_builder import (
    IntradayBacktestCandidate,
    IntradayBacktestCandidateBuilder,
)
from src.application.services.intraday_backtest_execution import (
    compute_intraday_pnl,
    size_intraday_position,
)
from src.application.use_case.pre_open_post_open_gates_use_case import (
    PreOpenPostOpenGatesRequest,
    PreOpenPostOpenGatesUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.pre_open_post_open_assessment import (
    PreOpenPostOpenCandidate,
    PreOpenPostOpenDecision,
)


@dataclass(frozen=True)
class IntradayBacktestSimulationResult:
    """The aggregate results of the simulation run."""

    trades: list[IntradayBacktestTrade]
    final_equity: Decimal
    equity_curve: list[Decimal]
    trading_days: int
    days_with_trades: int
    warnings: list[str]


class IntradayBacktestSimulator:
    """Orchestrates daily walk-forward simulations of the intraday strategy."""

    def __init__(
        self,
        *,
        market_repository: MarketDataRepository,
        candidate_builder: IntradayBacktestCandidateBuilder,
        confirm_use_case: PreOpenPostOpenGatesUseCase | None = None,
        iev_repository=None,
    ) -> None:
        self._market_repo = market_repository
        self._candidate_builder = candidate_builder
        self._confirm = confirm_use_case or PreOpenPostOpenGatesUseCase()
        self._iev_repo = iev_repository

    def run(
        self,
        *,
        tickers: list[str],
        trading_dates: list[date],
        request: IntradayBacktestRequest,
    ) -> IntradayBacktestSimulationResult:
        """Run daily-OHLC proxy simulation for the set of tickers and trading dates."""
        cash = request.capital
        equity_curve: list[Decimal] = [cash]
        all_trades: list[IntradayBacktestTrade] = []
        days_with_trades = 0

        for d in trading_dates:
            day_trades: list[IntradayBacktestTrade] = []

            # ── Step 1: build pre-open candidates as of d-1 ──────────────────
            candidates: list[IntradayBacktestCandidate] = []
            for ticker in tickers:
                c = self._candidate_builder.build(ticker=ticker, trade_date=d, request=request)
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
            candidate_map: dict[str, IntradayBacktestCandidate] = {}
            today_candles: dict[str, Candle] = {}

            for cand in candidates:
                raw = self._market_repo.get_candles(cand.ticker, start_date=d, end_date=d)
                if not raw:
                    continue
                today_candle = raw[0]
                today_candles[cand.ticker] = today_candle
                candidate_map[cand.ticker] = cand
                conf_candidates.append(
                    PreOpenPostOpenCandidate(
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
                        opening_broker_backing_tag=cand.opening_broker_backing_tag,
                        fvwap_discount_pct=(
                            Decimal(str(cand.fvwap_discount_pct))
                            if cand.fvwap_discount_pct is not None
                            else None
                        ),
                    )
                )

            if not conf_candidates:
                equity_curve.append(cash)
                continue

            confirm_result = self._confirm.execute(
                PreOpenPostOpenGatesRequest(
                    candidates=conf_candidates,
                    run_date=d,
                    max_stop_pct=request.max_stop_pct,
                    tick_friction_gate=False,
                    regime_gate_enabled=False,
                )
            )

            # ── Step 3: filter, rank, and cap ────────────────────────────────
            accepted_decisions = {PreOpenPostOpenDecision.ENTER}
            if request.include_wait:
                accepted_decisions.add(PreOpenPostOpenDecision.WAIT)

            entries = [
                conf for conf in confirm_result.confirmations if conf.decision in accepted_decisions
            ]

            def _rank_key(conf):
                cand = candidate_map.get(conf.ticker)
                opening_broker_backing_score = cand.opening_broker_backing_score if cand else None
                fvwap = cand.fvwap_discount_pct if cand else None
                stop_pct = float(conf.stop_pct) if conf.stop_pct else 999.0
                return (
                    -(opening_broker_backing_score or 0.0),
                    -(fvwap or 0.0),
                    stop_pct,
                    conf.ticker,
                )

            entries.sort(key=_rank_key)
            entries = entries[: request.max_daily_positions]

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

                lots, shares = size_intraday_position(
                    entry,
                    stop,
                    request.capital,
                    request.risk_pct,
                    cash,
                    request.cost_bps,
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

                pnl, gross_pct, net_pct, cost_total = compute_intraday_pnl(
                    shares,
                    entry,
                    exit_price,
                    request.cost_bps,
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
                    opening_broker_backing_tag=cand.opening_broker_backing_tag,
                    opening_broker_backing_score=cand.opening_broker_backing_score,
                    opening_broker_buy_streak=cand.opening_broker_buy_streak,
                    fvwap_discount_pct=cand.fvwap_discount_pct,
                    prev_high=cand.prev_high,
                    entry_range_low=cand.entry_range_low,
                    entry_range_high=cand.entry_range_high,
                    same_day_both_breached=both_breached,
                )
                day_trades.append(trade)

            all_trades.extend(day_trades)
            if day_trades:
                days_with_trades += 1

            # ── Step 5: end-of-day equity (no overnight positions) ────────────
            equity = cash
            equity_curve.append(equity)

        # ── Warnings ──────────────────────────────────────────────────────────
        warnings: list[str] = []
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
        warnings.extend(
            [
                "Same-day H/L ordering is conservative: both-breached cases assume stop hit first.",
                "Opening price = candle.open (IDX 09:00 call-auction clearing price proxy).",
                "Tick-friction and regime gates are NOT replayed in this daily-OHLC proxy.",
            ]
        )
        if not request.include_wait:
            warnings.append(
                "WAIT decisions are skipped by default; use --include-wait to include them."
            )

        both_count = sum(1 for t in all_trades if t.same_day_both_breached)
        if all_trades and both_count / len(all_trades) > 0.15:
            ratio_pct = both_count / len(all_trades)
            warnings.append(
                f"WARNING: {both_count}/{len(all_trades)} trades ({ratio_pct:.0%}) "
                "had same-day H/L ambiguity — daily OHLC proxy may be too coarse for this universe."
            )

        return IntradayBacktestSimulationResult(
            trades=all_trades,
            final_equity=cash,
            equity_curve=equity_curve,
            trading_days=len(trading_dates),
            days_with_trades=days_with_trades,
            warnings=warnings,
        )
