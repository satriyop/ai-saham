"""
PreOpenScreenUseCase — orchestrates the pre-open screening workflow.

Steps:
  1-3. Fetch movers from Stockbit browser, filter by IEV >= threshold,
       apply top-N cap if configured
  4.   Technical context: ATR(14), RSI(14), prev close/high/low
  5.   ATR-scaled entry range (Improvement #3)
  6.   Order book bid -> gap% (skipped in fast mode)
  7.   ATR-based stop (or legacy fixed-pct fallback)
  8.   Opening broker-backing tag + Foreign VWAP (Improvements #1 & #2)
  9.   AI research per ticker (optional)
  10.  Build ScreenerCandidate

Entry model:
  IDX 08:45-09:00 is a call auction. Entry range is derived from yesterday's
  close +/- ATR (not bid+tick). Trader enters only if opening price falls in range.

Layer: Application
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from src.application.services.pre_open_broker_signals import (
    assess_pre_open_broker_signals,
)
from src.application.services.pre_open_candidate_builder import (
    build_pre_open_candidate,
)
from src.application.services.pre_open_entry_plan import (
    classify_pre_open_trend,
    compute_pre_open_entry_price,
    compute_pre_open_entry_range,
    compute_pre_open_stop_loss,
)
from src.application.services.pre_open_order_book_context import (
    build_pre_open_order_book_context,
)
from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.application.services.pre_open_technical_context import (
    build_pre_open_technical_context,
)
from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.ports.ticker_notation_provider import TickerNotationProvider
from src.domain.value_objects.screener_result import (
    PreOpenScreenResult,
    ScreenerCandidate,
)

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass
class PreOpenScreenRequest:
    config: PreOpenScreenConfig
    run_date: date | None = None


@dataclass(frozen=True)
class PreOpenFilterReject:
    """Hard-filter reject for observation records (ADR-048 follow-up)."""

    ticker: str
    screen_result: str  # e.g. rejected_filter_speculative, rejected_filter_floor
    reason: str
    iev: int | None = None


@dataclass
class PreOpenScreenResponse:
    result: PreOpenScreenResult
    warnings: list[str]
    raw_movers: "list"
    filter_rejects: list[PreOpenFilterReject] | None = None


class PreOpenScreenUseCase:
    """Orchestrates the pre-open screening workflow.

    Dependencies:
        browser: Provides movers list and order book data
        repository: Local SQLite market data cache
        registry: Indicator registry for ATR / SMA / RSI computation
        broker_repository: Optional - enables accumulation backing + Foreign VWAP
        ai_explainer: Optional - generates AI research summary per ticker
    """

    def __init__(
        self,
        browser: BrowserDataProvider,
        repository: "MarketDataRepository",
        registry: "IndicatorRegistry",
        broker_repository: "BrokerDataRepository | None" = None,
        ai_explainer=None,
        ticker_notation_provider: "TickerNotationProvider | None" = None,
    ) -> None:
        self._browser = browser
        self._repository = repository
        self._registry = registry
        self._broker_repository = broker_repository
        self._ai_explainer = ai_explainer
        self._ticker_notation_provider = ticker_notation_provider

    def execute(self, request: PreOpenScreenRequest) -> PreOpenScreenResponse:
        config = request.config
        run_date = request.run_date or date.today()
        warnings: list[str] = []

        # Steps 1-3: Fetch movers, filter by IEV, apply top-N cap
        raw_movers = self._browser.fetch_preopen_movers(config.iev_min)
        total_seen = len(raw_movers)

        movers = raw_movers
        if config.top_n is not None:
            movers = movers[: config.top_n]

        if config.iep_min is not None:
            before = len(movers)
            movers = [m for m in movers if m.iep is None or m.iep >= config.iep_min]
            dropped = before - len(movers)
            if dropped:
                warnings.append(
                    f"IEP floor: filtered out {dropped} movers with IEP < {config.iep_min:,}"
                )

        candidates: list[ScreenerCandidate] = []
        filter_rejects: list[PreOpenFilterReject] = []

        for mover in movers:
            ticker = mover.ticker

            # Speculative symbol filter: skip warrants (-W), rights (-R), bonds (-L)
            if config.exclude_suffix_pattern and re.search(
                config.exclude_suffix_pattern, ticker, re.IGNORECASE
            ):
                reason = f"{ticker}: SKIP_SPECULATIVE — matches excluded suffix pattern"
                warnings.append(reason)
                filter_rejects.append(
                    PreOpenFilterReject(
                        ticker=ticker,
                        screen_result="rejected_filter_speculative",
                        reason=reason,
                        iev=getattr(mover, "iev", None),
                    )
                )
                continue

            # Step 4: Technical context - ATR, RSI, SMA, prev OHLC + candles
            ctx = build_pre_open_technical_context(
                repository=self._repository,
                registry=self._registry,
                ticker=ticker,
                sma_period=config.sma_period,
                rsi_period=config.rsi_period,
                atr_period=config.atr_period,
                history_days=config.history_days,
            )
            if ctx["warning"]:
                warnings.append(ctx["warning"])

            prev_close = ctx["prev_close"]
            prev_high = ctx["prev_high"]
            prev_low = ctx["prev_low"]
            rsi_val = ctx["rsi"]
            sma_val = ctx["sma"]
            atr_val = ctx["atr"]
            candles = ctx["candles"]

            # Floor-price filter: skip if previous close or IEP is at or below IDX floor price (50)
            if prev_close is not None and prev_close <= 50:
                reason = (
                    f"{ticker}: SKIP_FLOOR — previous close is at the IDX floor price (50)"
                )
                warnings.append(reason)
                filter_rejects.append(
                    PreOpenFilterReject(
                        ticker=ticker,
                        screen_result="rejected_filter_floor",
                        reason=reason,
                        iev=getattr(mover, "iev", None),
                    )
                )
                continue
            if mover.iep is not None and mover.iep <= 50:
                reason = f"{ticker}: SKIP_FLOOR — IEP is at the IDX floor price (50)"
                warnings.append(reason)
                filter_rejects.append(
                    PreOpenFilterReject(
                        ticker=ticker,
                        screen_result="rejected_filter_floor",
                        reason=reason,
                        iev=getattr(mover, "iev", None),
                    )
                )
                continue

            # Speculative symbol filter: skip stocks with insufficient history for ATR/RSI
            if len(candles) < config.min_history_days:
                reason = (
                    f"{ticker}: SKIP_SPECULATIVE — only {len(candles)} days history"
                    f" (min {config.min_history_days})"
                )
                warnings.append(reason)
                filter_rejects.append(
                    PreOpenFilterReject(
                        ticker=ticker,
                        screen_result="rejected_filter_history",
                        reason=reason,
                        iev=getattr(mover, "iev", None),
                    )
                )
                continue

            # Phase 2.1: IEV intensity
            iev_intensity: float | None = None
            unusual_volume = False
            if config.iev_intensity_enabled and candles:
                avg_daily_volume = sum(c.volume for c in candles[-20:]) / min(len(candles), 20)
                avg_5min_volume = avg_daily_volume / 78
                if avg_5min_volume > 0:
                    iev_intensity = mover.iev / avg_5min_volume
                    if iev_intensity > config.iev_intensity_unusual_threshold:
                        unusual_volume = True

            # Step 5 (Improvement #3): ATR-scaled entry range
            effective_band, entry_range_low, entry_range_high = compute_pre_open_entry_range(
                prev_close=prev_close,
                atr=atr_val,
                config=config,
            )

            # Step 6: Order book bid+offer -> gap%, spread%, bid/offer imbalance
            ob_ctx = build_pre_open_order_book_context(
                browser=self._browser,
                ticker=ticker,
                mover=mover,
                prev_close=prev_close,
                effective_band=effective_band,
                fast_mode=config.fast_mode,
            )
            warnings.extend(ob_ctx.warnings)

            # Step 7: Entry price and ATR-based stop
            entry_price = compute_pre_open_entry_price(
                prev_close=prev_close,
                bid_price=ob_ctx.bid_price,
                config=config,
            )

            stop_loss_price = compute_pre_open_stop_loss(
                entry_price=entry_price,
                atr=atr_val,
                config=config,
            )

            # Floor-price guard: discard tickers with no profit room entirely
            if (
                entry_price is not None
                and stop_loss_price is not None
                and entry_price <= stop_loss_price
            ):
                reason = (
                    f"{ticker}: SKIP_FLOOR — entry <= stop (one_r=0, at price floor)"
                )
                warnings.append(reason)
                filter_rejects.append(
                    PreOpenFilterReject(
                        ticker=ticker,
                        screen_result="rejected_filter_floor",
                        reason=reason,
                        iev=getattr(mover, "iev", None),
                    )
                )
                continue

            # Trend classification
            trend_signal = classify_pre_open_trend(
                gap_pct=ob_ctx.gap_pct,
                rsi=rsi_val,
                effective_band=effective_band,
                rsi_overbought=config.rsi_overbought_threshold,
                close=prev_close,
                sma=sma_val,
            )

            # Step 8 (Improvements #1 + #2): opening broker backing + Foreign VWAP
            opening_broker_backing_score: float | None = None
            opening_broker_backing_tag: str | None = None
            opening_broker_buy_streak: int | None = None
            foreign_vwap: Decimal | None = None
            fvwap_discount_pct: float | None = None

            if self._broker_repository is not None:
                current_price = (
                    ob_ctx.bid_price if ob_ctx.bid_price is not None else prev_close
                )
                broker_sig = assess_pre_open_broker_signals(
                    self._broker_repository,
                    ticker=ticker,
                    candles=candles,
                    current_price=current_price,
                    broker_backing_window=config.broker_backing_window_days,
                    broker_backing_threshold=config.broker_backing_threshold,
                    fvwap_period=config.fvwap_period,
                )
                opening_broker_backing_score = broker_sig.opening_broker_backing_score
                opening_broker_backing_tag = broker_sig.opening_broker_backing_tag
                opening_broker_buy_streak = broker_sig.opening_broker_buy_streak
                foreign_vwap = broker_sig.foreign_vwap
                fvwap_discount_pct = broker_sig.fvwap_discount_pct

            ticker_notation = None
            if self._ticker_notation_provider is not None:
                ticker_notation = self._ticker_notation_provider.get_notation(ticker)

            # Step 9: AI research (optional)
            ai_summary = self._research_ticker(ticker)

            # Step 10: Build candidate
            candidates.append(
                build_pre_open_candidate(
                    ticker=ticker,
                    mover=mover,
                    entry_price=entry_price,
                    stop_loss_price=stop_loss_price,
                    capital=config.capital,
                    trend_signal=trend_signal,
                    rsi=rsi_val,
                    sma=sma_val,
                    ai_summary=ai_summary,
                    atr=atr_val,
                    prev_close=prev_close,
                    prev_high=prev_high,
                    prev_low=prev_low,
                    gap_pct=ob_ctx.gap_pct,
                    entry_range_low=entry_range_low,
                    entry_range_high=entry_range_high,
                    opening_broker_backing_score=opening_broker_backing_score,
                    opening_broker_backing_tag=opening_broker_backing_tag,
                    opening_broker_buy_streak=opening_broker_buy_streak,
                    foreign_vwap=foreign_vwap,
                    fvwap_discount_pct=fvwap_discount_pct,
                    iev_intensity=iev_intensity,
                    unusual_volume=unusual_volume,
                    best_offer=ob_ctx.best_offer,
                    best_offer_lots=ob_ctx.best_offer_lots,
                    spread_pct=ob_ctx.spread_pct,
                    bid_offer_imbalance=ob_ctx.bid_offer_imbalance,
                    ticker_notation=ticker_notation,
                )
            )

        return PreOpenScreenResponse(
            result=PreOpenScreenResult(
                screened_date=run_date,
                iev_min=config.iev_min,
                total_movers_seen=total_seen,
                candidates=candidates,
            ),
            warnings=warnings,
            raw_movers=raw_movers,
            filter_rejects=filter_rejects,
        )

    # ── Private helpers ────────────────────────────────────────────────────

    def _research_ticker(self, ticker: str) -> str | None:
        if self._ai_explainer is None:
            return None
        try:
            return self._ai_explainer.research(ticker)
        except Exception:
            return None
