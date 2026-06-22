"""
PreOpenScreenUseCase — orchestrates the pre-open screening workflow.

Steps:
  1-3. Fetch movers from Stockbit browser, filter by IEV >= threshold,
       apply top-N cap if configured
  4.   Technical context: ATR(14), RSI(14), prev close/high/low
  5.   ATR-scaled entry range (Improvement #3)
  6.   Order book bid → gap% (skipped in fast mode)
  7.   ATR-based stop (or legacy fixed-pct fallback)
  8.   Accumulation backing tag + Foreign VWAP (Improvements #1 & #2)
  9.   AI research per ticker (optional)
  10.  Build ScreenerCandidate

Entry model:
  IDX 08:45–09:00 is a call auction. Entry range is derived from yesterday's
  close ± ATR (not bid+tick). Trader enters only if opening price falls in range.

Layer: Application
"""

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.application.services.indicator_registry import IndicatorRegistry
from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.ticker_notation_provider import TickerNotationProvider
from src.domain.value_objects.screener_result import (
    PreOpenScreenResult,
    ScreenerCandidate,
)
from src.infrastructure.browser.stockbit_browser import (
    entry_price_from_bid,
    suggested_limit_from_close,
)

# TYPE_CHECKING import to avoid circular dependency
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.ports.broker_data_repository import BrokerDataRepository


@dataclass
class PreOpenScreenConfig:
    """Screening parameters, loaded from config YAML or overridden by CLI flags."""

    iev_min: int = 100_000
    capital: Decimal = Decimal("3000000")
    tick_above: int = 1                          # legacy reference only
    stop_loss_pct: Decimal = Decimal("0.20")     # legacy fallback
    sma_period: int = 20
    rsi_period: int = 14
    history_days: int = 365
    atr_period: int = 14
    atr_multiplier: Decimal = Decimal("1.0")
    max_stop_pct: Decimal = Decimal("0.07")
    use_atr_stop: bool = True
    max_gap_pct: Decimal = Decimal("0.03")       # fallback when no ATR
    suggested_limit_pct: Decimal = Decimal("0.005")
    rsi_overbought_threshold: Decimal = Decimal("75")
    top_n: int | None = None
    fast_mode: bool = False
    iep_min: int | None = None  # IEP floor — exclude movers with IEP below this; None disables
    # Improvement #3 — ATR-scaled entry range
    use_atr_range: bool = True
    atr_range_cap_min: Decimal = Decimal("0.01")  # never narrower than 1%
    atr_range_cap_max: Decimal = Decimal("0.05")  # never wider than 5%
    # Improvement #1 — accumulation backing
    accum_window_days: int = 7
    accum_backed_threshold: float = 50.0
    # Improvement #2 — foreign VWAP
    fvwap_period: int = 20
    # Speculative symbol filter (Phase 1.1)
    exclude_suffix_pattern: str = r"-(W|R|L)$"
    min_history_days: int = 20
    # IEV intensity signal (Phase 2.1)
    iev_intensity_enabled: bool = True
    iev_intensity_unusual_threshold: float = 5.0
    iev_intensity_auto_downgrade: bool = False
    # Pre-open bid pressure filter
    min_bid_pressure_preopen: float = 0.0  # 0.0 = disabled; 0.40 = require 40% bid dominance

    @classmethod
    def from_yaml(cls, data: dict) -> "PreOpenScreenConfig":
        """Parse from pre-open screener config YAML. All new keys have safe defaults."""
        screener = data.get("screener", {})
        entry = data.get("entry", {})
        risk = data.get("risk", {})
        analysis = data.get("analysis", {})

        top_n_raw = screener.get("top_n", None)

        return cls(
            iev_min=int(screener.get("iev_min", 100_000)),
            capital=Decimal(str(entry.get("capital", 3_000_000))),
            tick_above=int(entry.get("tick_above", 1)),
            stop_loss_pct=Decimal(str(risk.get("stop_loss_pct", 0.20))),
            sma_period=int(analysis.get("sma_period", 20)),
            rsi_period=int(analysis.get("rsi_period", 14)),
            history_days=int(analysis.get("days", 365)),
            atr_period=int(analysis.get("atr_period", 14)),
            atr_multiplier=Decimal(str(risk.get("atr_multiplier", 1.0))),
            max_stop_pct=Decimal(str(risk.get("max_stop_pct", 0.07))),
            use_atr_stop=bool(risk.get("use_atr_stop", True)),
            max_gap_pct=Decimal(str(entry.get("max_gap_pct", 0.03))),
            suggested_limit_pct=Decimal(str(entry.get("suggested_limit_pct", 0.005))),
            rsi_overbought_threshold=Decimal(
                str(analysis.get("rsi_overbought_threshold", 75))
            ),
            top_n=int(top_n_raw) if top_n_raw is not None else None,
            fast_mode=bool(screener.get("fast_mode", False)),
            iep_min=int(screener["iep_min"]) if screener.get("iep_min") is not None else None,
            use_atr_range=bool(analysis.get("use_atr_range", True)),
            atr_range_cap_min=Decimal(str(analysis.get("atr_range_cap_min", 0.01))),
            atr_range_cap_max=Decimal(str(analysis.get("atr_range_cap_max", 0.05))),
            accum_window_days=int(analysis.get("accum_window_days", 7)),
            accum_backed_threshold=float(analysis.get("accum_backed_threshold", 50.0)),
            fvwap_period=int(analysis.get("fvwap_period", 20)),
            exclude_suffix_pattern=str(
                data.get("filters", {}).get("exclude_suffix_pattern", r"-(W|R|L)$")
            ),
            min_history_days=int(data.get("filters", {}).get("min_history_days", 20)),
            iev_intensity_enabled=bool(analysis.get("iev_intensity_enabled", True)),
            iev_intensity_unusual_threshold=float(
                analysis.get("iev_intensity_unusual_threshold", 5.0)
            ),
            iev_intensity_auto_downgrade=bool(
                analysis.get("iev_intensity_auto_downgrade", False)
            ),
            min_bid_pressure_preopen=float(screener.get("min_bid_pressure_preopen", 0.0)),
        )


@dataclass
class PreOpenScreenRequest:
    config: PreOpenScreenConfig
    run_date: date | None = None


@dataclass
class PreOpenScreenResponse:
    result: PreOpenScreenResult
    warnings: list[str]
    raw_movers: "list"  # list[MoverData] — all movers returned by IEV API before top-N cap


class PreOpenScreenUseCase:
    """Orchestrates the pre-open screening workflow.

    Dependencies:
        browser: Provides movers list and order book data
        repository: Local SQLite market data cache
        registry: Indicator registry for ATR / SMA / RSI computation
        broker_repository: Optional — enables accumulation backing + Foreign VWAP
        ai_explainer: Optional — generates AI research summary per ticker
    """

    def __init__(
        self,
        browser: BrowserDataProvider,
        repository: MarketDataRepository,
        registry: IndicatorRegistry,
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

        for mover in movers:
            ticker = mover.ticker

            # Speculative symbol filter: skip warrants (-W), rights (-R), bonds (-L)
            if config.exclude_suffix_pattern and re.search(
                config.exclude_suffix_pattern, ticker, re.IGNORECASE
            ):
                warnings.append(f"{ticker}: SKIP_SPECULATIVE — matches excluded suffix pattern")
                continue

            # Step 4: Technical context — ATR, RSI, SMA, prev OHLC + candles
            ctx = self._assess_context(
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

            # Speculative symbol filter: skip stocks with insufficient history for ATR/RSI
            if len(candles) < config.min_history_days:
                warnings.append(
                    f"{ticker}: SKIP_SPECULATIVE — only {len(candles)} days history"
                    f" (min {config.min_history_days})"
                )
                continue

            # Phase 2.1: IEV intensity — compares mover IEV to the stock's typical 5-min volume
            # Formula: IEV_Intensity = IEV / (ADV_20d / 78)  where 78 ≈ 5-min bars per day
            # High intensity (> threshold) = unusual interest; NOT necessarily manipulation.
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
            effective_band, entry_range_low, entry_range_high = self._compute_entry_range(
                prev_close=prev_close,
                atr=atr_val,
                config=config,
            )

            # Step 6: Order book bid+offer → gap%, spread%, bid/offer imbalance (skipped in fast mode)
            gap_pct: Decimal | None = None
            ob = None
            best_offer: Decimal | None = None
            best_offer_lots: int | None = None
            spread_pct: Decimal | None = None
            bid_offer_imbalance: float | None = None

            if not config.fast_mode:
                tob = self._browser.fetch_order_book_top_of_book(ticker)
                ob = tob.bid if tob else None
                if ob is not None:
                    if prev_close is not None and prev_close > 0:
                        gap_pct = (
                            (ob.price - prev_close) / prev_close * 100
                        ).quantize(Decimal("0.01"))
                        if abs(gap_pct) > effective_band * 100:
                            warnings.append(
                                f"{ticker}: Gap {gap_pct:+.1f}% exceeds ±{float(effective_band*100):.1f}% ATR band"
                            )
                    if tob and tob.offer:
                        best_offer = tob.offer.price
                        best_offer_lots = tob.offer.volume
                        spread_pct = (
                            (tob.offer.price - ob.price) / ob.price * 100
                        ).quantize(Decimal("0.01"))
                        total_lots = ob.volume + tob.offer.volume
                        if total_lots > 0:
                            bid_offer_imbalance = round(ob.volume / total_lots, 3)
                else:
                    if mover.iep is not None and prev_close is not None and prev_close > 0:
                        gap_pct = (
                            (Decimal(mover.iep) - prev_close) / prev_close * 100
                        ).quantize(Decimal("0.01"))
                        warnings.append(
                            f"{ticker}: No order book bid — gap% from IEP ({mover.iep})"
                        )
                    else:
                        warnings.append(
                            f"{ticker}: No order book data — gap% not computed"
                        )

            # Suggested limit order price
            entry_price: Decimal | None = None
            if prev_close is not None and prev_close > 0:
                entry_price = suggested_limit_from_close(prev_close, config.suggested_limit_pct)
            elif ob is not None:
                entry_price = entry_price_from_bid(ob.price, config.tick_above)

            # Step 7: ATR-based stop
            stop_loss_price: Decimal | None = None
            if entry_price is not None:
                if config.use_atr_stop and atr_val is not None:
                    raw_stop = entry_price - (config.atr_multiplier * atr_val)
                    floor_stop = entry_price * (1 - config.max_stop_pct)
                    stop_loss_price = max(raw_stop, floor_stop).quantize(Decimal("1"))
                else:
                    stop_loss_price = (
                        entry_price * (1 - config.stop_loss_pct)
                    ).quantize(Decimal("1"))

            # Floor-price guard: discard tickers with no profit room entirely
            if entry_price is not None and stop_loss_price is not None and entry_price <= stop_loss_price:
                warnings.append(f"{ticker}: SKIP_FLOOR — entry <= stop (one_r=0, at price floor)")
                continue

            # Trend classification — uses effective ATR-based band as gap threshold
            trend_signal = self._classify_trend_v2(
                gap_pct=gap_pct,
                rsi=rsi_val,
                effective_band=effective_band,
                rsi_overbought=config.rsi_overbought_threshold,
                close=prev_close,
                sma=sma_val,
            )

            # Step 8 (Improvements #1 + #2): Accumulation backing + Foreign VWAP
            # Broker summaries loaded once, reused by both signals.
            accum_score: float | None = None
            accum_tag: str | None = None
            accum_streak: int | None = None
            foreign_vwap: Decimal | None = None
            fvwap_discount_pct: float | None = None

            if self._broker_repository is not None:
                broker_ctx = self._assess_broker_signals(
                    ticker=ticker,
                    candles=candles,
                    current_price=ob.price if ob else prev_close,
                    accum_window=config.accum_window_days,
                    accum_threshold=config.accum_backed_threshold,
                    fvwap_period=config.fvwap_period,
                )
                accum_score = broker_ctx["accum_score"]
                accum_tag = broker_ctx["accum_tag"]
                accum_streak = broker_ctx["accum_streak"]
                foreign_vwap = broker_ctx["foreign_vwap"]
                fvwap_discount_pct = broker_ctx["fvwap_discount_pct"]

            ticker_notation = None
            if self._ticker_notation_provider is not None:
                ticker_notation = self._ticker_notation_provider.get_notation(ticker)

            # Step 9: AI research (optional)
            ai_summary = self._research_ticker(ticker)

            # Step 10: Build candidate
            candidates.append(
                ScreenerCandidate(
                    ticker=ticker,
                    iev=mover.iev,
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
                    gap_pct=gap_pct,
                    entry_range_low=entry_range_low,
                    entry_range_high=entry_range_high,
                    accum_score=accum_score,
                    accum_tag=accum_tag,
                    accum_streak=accum_streak,
                    foreign_vwap=foreign_vwap,
                    fvwap_discount_pct=fvwap_discount_pct,
                    iev_intensity=iev_intensity,
                    unusual_volume=unusual_volume,
                    best_offer=best_offer,
                    best_offer_lots=best_offer_lots,
                    spread_pct=spread_pct,
                    bid_offer_imbalance=bid_offer_imbalance,
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
        )

    # ── Private helpers ────────────────────────────────────────────────────

    def _assess_context(
        self,
        ticker: str,
        sma_period: int,
        rsi_period: int,
        atr_period: int,
        history_days: int,
    ) -> dict:
        """Load candles and compute ATR, RSI, SMA, prev OHLC.

        Returns dict with keys: prev_close, prev_high, prev_low, rsi, sma, atr,
        candles (list), warning. All indicator values default to None on failure.
        """
        empty = {
            "prev_close": None, "prev_high": None, "prev_low": None,
            "rsi": None, "sma": None, "atr": None,
            "candles": [], "warning": None,
        }

        try:
            candles = self._repository.get_candles(ticker.upper())
            if not candles:
                empty["warning"] = (
                    f"{ticker}: No cached data - run 'saham fetch market {ticker} --days 365' first"
                )
                return empty

            if len(candles) > history_days:
                candles = candles[-history_days:]

            prev = candles[-1]

            sma_values = self._registry.compute("SMA", candles, sma_period)
            rsi_values = self._registry.compute("RSI", candles, rsi_period)
            atr_values = self._registry.compute("ATR", candles, atr_period)

            return {
                "prev_close": prev.close,
                "prev_high": prev.high,
                "prev_low": prev.low,
                "sma": sma_values[-1][1] if sma_values else None,
                "rsi": rsi_values[-1][1] if rsi_values else None,
                "atr": atr_values[-1][1] if atr_values else None,
                "candles": candles,
                "warning": None,
            }

        except Exception as e:
            empty["warning"] = f"{ticker}: Context assessment failed — {e}"
            return empty

    @staticmethod
    def _compute_entry_range(
        prev_close: Decimal | None,
        atr: Decimal | None,
        config: "PreOpenScreenConfig",
    ) -> tuple[Decimal, Decimal | None, Decimal | None]:
        """Compute effective gap band and entry range.

        Improvement #3: use ATR-scaled band (ATR/prev_close) instead of fixed %.
        Returns (effective_band, range_low, range_high).
        """
        # Determine the effective band
        if (
            config.use_atr_range
            and atr is not None
            and prev_close is not None
            and prev_close > 0
        ):
            atr_pct = atr / prev_close
            effective_band = max(
                config.atr_range_cap_min,
                min(atr_pct, config.atr_range_cap_max),
            )
        else:
            effective_band = config.max_gap_pct

        if prev_close is None or prev_close <= 0:
            return effective_band, None, None

        low = (prev_close * (1 - effective_band)).quantize(Decimal("1"))
        high = (prev_close * (1 + effective_band)).quantize(Decimal("1"))
        return effective_band, low, high

    def _assess_broker_signals(
        self,
        ticker: str,
        candles: list,
        current_price: Decimal | None,
        accum_window: int,
        accum_threshold: float,
        fvwap_period: int,
    ) -> dict:
        """Load broker summaries once; compute accumulation tag + Foreign VWAP.

        Returns dict with: accum_score, accum_tag, accum_streak,
        foreign_vwap, fvwap_discount_pct. All None on failure or missing data.
        """
        empty = {
            "accum_score": None, "accum_tag": None, "accum_streak": None,
            "foreign_vwap": None, "fvwap_discount_pct": None,
        }

        try:
            today = date.today()
            start = today - timedelta(days=accum_window + fvwap_period + 10)
            summaries = self._broker_repository.get_broker_summaries(
                ticker=ticker, start_date=start, end_date=today
            )
        except Exception:
            return empty

        if not summaries:
            return empty

        result = dict(empty)

        # ── Improvement #1: Accumulation backing ──────────────────────────
        cutoff = date.today() - timedelta(days=accum_window)
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

            # Score: consistency (40pts) + exponential streak (30pts, τ=7d)
            score = round(
                ratio * 40.0 + 30.0 * (1.0 - math.exp(-streak / 7.0)),
                1,
            )

            if score >= accum_threshold:
                tag = "BACKED"
            elif ratio < 0.3:
                tag = "DISTRIBUTING"
            else:
                tag = "UNCONFIRMED"

            result["accum_score"] = score
            result["accum_tag"] = tag
            result["accum_streak"] = streak

        # ── Improvement #2: Foreign VWAP ──────────────────────────────────
        if candles and current_price is not None and current_price > 0:
            try:
                from plugins.indicators.foreign_vwap import ForeignVWAPIndicator
                indicator = ForeignVWAPIndicator()
                indicator.set_broker_data(summaries)
                vwap_values = indicator.compute(
                    candles[-max(len(candles), fvwap_period):], fvwap_period
                )
                if vwap_values:
                    fvwap = vwap_values[-1]
                    if fvwap > 0:
                        result["foreign_vwap"] = fvwap
                        result["fvwap_discount_pct"] = round(
                            float((fvwap - current_price) / current_price * 100), 2
                        )
            except Exception:
                pass

        return result

    @staticmethod
    def _classify_trend_v2(
        gap_pct: Decimal | None,
        rsi: Decimal | None,
        effective_band: Decimal,
        rsi_overbought: Decimal,
        close: Decimal | None = None,
        sma: Decimal | None = None,
    ) -> str | None:
        """Classify trend using gap% (vs effective ATR band) and RSI gate."""
        if rsi is not None and rsi > rsi_overbought:
            return "BEARISH"

        if gap_pct is not None and abs(gap_pct) > effective_band * 100:
            return "BEARISH"

        if rsi is not None and Decimal("30") < rsi < Decimal("65"):
            if gap_pct is not None and abs(gap_pct) <= Decimal("2"):
                return "BULLISH"

        # Legacy SMA fallback for fast mode (no gap data)
        if gap_pct is None and close is not None and sma is not None:
            return _classify_trend_legacy(close, sma, rsi)

        return "NEUTRAL"

    def _research_ticker(self, ticker: str) -> str | None:
        if self._ai_explainer is None:
            return None
        try:
            return self._ai_explainer.research(ticker)
        except Exception:
            return None


def _classify_trend_legacy(
    close: Decimal | None,
    sma: Decimal | None,
    rsi: Decimal | None,
) -> str | None:
    """Original SMA-based trend classifier (fallback for fast mode)."""
    if close is None or sma is None or rsi is None:
        return None
    above_sma = close > sma
    overbought = rsi > Decimal("65")
    if above_sma and not overbought:
        return "BULLISH"
    if not above_sma and overbought:
        return "BEARISH"
    if above_sma and rsi < Decimal("40"):
        return "DIP_BUY"
    return "NEUTRAL"
