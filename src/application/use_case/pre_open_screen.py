"""
PreOpenScreenUseCase — orchestrates the pre-open screening workflow.

Steps:
  1-3. Fetch movers from Stockbit browser, filter by IEV >= threshold,
       apply top-N cap if configured
  4.   Technical context: ATR(14), RSI(14), prev close/high/low
  5.   Compute entry range and gap% (skipped in fast mode)
  6.   Fetch order book best bid (skipped in fast mode)
  7.   Compute ATR-based stop (or legacy fixed-pct fallback)
  8.   AI research per ticker (optional)
  9.   Build ScreenerCandidate list

Entry model (replaces legacy bid+tick):
  IDX 08:45–09:00 is a call auction — the clearing price is set at 09:00
  from accumulated orders. "bid+tick" is a continuous-market construct and
  does not predict the opening price. Instead, this screener outputs:
    - entry_range: [prev_close * (1-max_gap), prev_close * (1+max_gap)]
    - entry_price: prev_close * (1 + suggested_limit_pct) — a starting
      limit to place after the opening price is known
  The trader then enters IF the opening price falls within the range.

Layer: Application
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.services.indicator_registry import IndicatorRegistry
from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.screener_result import (
    PreOpenScreenResult,
    ScreenerCandidate,
)
from src.infrastructure.browser.stockbit_browser import (
    entry_price_from_bid,
    suggested_limit_from_close,
)


@dataclass
class PreOpenScreenConfig:
    """Screening parameters, loaded from strategy.yaml or overridden by CLI flags."""

    iev_min: int = 100_000
    capital: Decimal = Decimal("3000000")
    tick_above: int = 1                          # legacy reference only
    stop_loss_pct: Decimal = Decimal("0.20")     # legacy fallback
    sma_period: int = 20
    rsi_period: int = 14
    history_days: int = 365
    # New fields (Change 2)
    atr_period: int = 14
    atr_multiplier: Decimal = Decimal("1.0")
    max_stop_pct: Decimal = Decimal("0.07")
    use_atr_stop: bool = True
    # New fields (Change 1 + 3)
    max_gap_pct: Decimal = Decimal("0.03")
    suggested_limit_pct: Decimal = Decimal("0.005")
    rsi_overbought_threshold: Decimal = Decimal("75")
    # New fields (Change 5)
    top_n: int | None = None
    fast_mode: bool = False

    @classmethod
    def from_yaml(cls, data: dict) -> "PreOpenScreenConfig":
        """Parse from strategy.yaml content dict. All new keys have safe defaults."""
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
        )


@dataclass
class PreOpenScreenRequest:
    config: PreOpenScreenConfig
    run_date: date | None = None


@dataclass
class PreOpenScreenResponse:
    result: PreOpenScreenResult
    warnings: list[str]


class PreOpenScreenUseCase:
    """Orchestrates the pre-open screening workflow.

    Dependencies:
        browser: Provides movers list and order book data
        repository: Local SQLite market data cache
        registry: Indicator registry for ATR / SMA / RSI computation
        ai_explainer: Optional — generates AI research summary per ticker
    """

    def __init__(
        self,
        browser: BrowserDataProvider,
        repository: MarketDataRepository,
        registry: IndicatorRegistry,
        ai_explainer=None,
    ) -> None:
        self._browser = browser
        self._repository = repository
        self._registry = registry
        self._ai_explainer = ai_explainer

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

        candidates: list[ScreenerCandidate] = []

        for mover in movers:
            ticker = mover.ticker

            # Step 4: Technical context — ATR, RSI, prev OHLC
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

            # Step 5: Entry range from prev_close
            entry_range_low: Decimal | None = None
            entry_range_high: Decimal | None = None
            if prev_close is not None and prev_close > 0:
                entry_range_low = (prev_close * (1 - config.max_gap_pct)).quantize(
                    Decimal("1")
                )
                entry_range_high = (prev_close * (1 + config.max_gap_pct)).quantize(
                    Decimal("1")
                )

            # Step 6: Order book bid → gap% (skipped in fast mode)
            gap_pct: Decimal | None = None
            entry_price: Decimal | None = None

            if not config.fast_mode:
                ob = self._browser.fetch_order_book_best_bid(ticker)
                if ob is not None:
                    if prev_close is not None and prev_close > 0:
                        gap_pct = (
                            (ob.price - prev_close) / prev_close * 100
                        ).quantize(Decimal("0.01"))
                        if abs(gap_pct) > config.max_gap_pct * 100:
                            warnings.append(
                                f"{ticker}: Gap {gap_pct:+.1f}% exceeds ±{float(config.max_gap_pct*100):.0f}% threshold"
                            )
                else:
                    warnings.append(
                        f"{ticker}: No order book data — gap% not computed"
                    )

            # Suggested limit order price
            if prev_close is not None and prev_close > 0:
                entry_price = suggested_limit_from_close(prev_close, config.suggested_limit_pct)
            elif not config.fast_mode and "ob" in dir() and ob is not None:
                # Fallback: legacy bid+tick if no prev_close
                entry_price = entry_price_from_bid(ob.price, config.tick_above)

            # Step 7: ATR-based stop (or legacy fallback)
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

            # Trend classification (Change 3)
            trend_signal = self._classify_trend_v2(
                gap_pct=gap_pct,
                rsi=rsi_val,
                max_gap_pct=config.max_gap_pct,
                rsi_overbought=config.rsi_overbought_threshold,
                close=prev_close,
                sma=sma_val,
            )

            # Step 8: AI research (optional)
            ai_summary = self._research_ticker(ticker)

            # Step 9: Build candidate
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

        Returns a dict with keys: prev_close, prev_high, prev_low, rsi, sma, atr, warning.
        All values default to None on failure.
        """
        empty = {
            "prev_close": None, "prev_high": None, "prev_low": None,
            "rsi": None, "sma": None, "atr": None, "warning": None,
        }

        try:
            candles = self._repository.get_candles(ticker.upper())
            if not candles:
                empty["warning"] = (
                    f"{ticker}: No cached data — run 'saham fetch {ticker}' first"
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
                "warning": None,
            }

        except Exception as e:
            empty["warning"] = f"{ticker}: Context assessment failed — {e}"
            return empty

    @staticmethod
    def _classify_trend_v2(
        gap_pct: Decimal | None,
        rsi: Decimal | None,
        max_gap_pct: Decimal,
        rsi_overbought: Decimal,
        close: Decimal | None = None,
        sma: Decimal | None = None,
    ) -> str | None:
        """Classify trend using gap% and RSI gate.

        BEARISH: RSI > overbought threshold, OR gap too large to trade safely.
        BULLISH: RSI in 30–65 range AND gap within safe band.
        NEUTRAL: everything else.

        Falls back to legacy SMA comparison when gap_pct is unavailable (fast mode).
        """
        if rsi is not None and rsi > rsi_overbought:
            return "BEARISH"

        if gap_pct is not None and abs(gap_pct) > max_gap_pct * 100:
            return "BEARISH"

        if rsi is not None and Decimal("30") < rsi < Decimal("65"):
            if gap_pct is None or abs(gap_pct) <= Decimal("2"):
                return "BULLISH"

        # Legacy fallback when no gap data (fast mode, no order book)
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
    """Original SMA-based trend classifier (kept for fallback)."""
    if close is None or sma is None or rsi is None:
        return None
    above_sma = close > sma
    oversold = rsi < Decimal("40")
    overbought = rsi > Decimal("65")
    if above_sma and not overbought:
        return "BULLISH"
    if not above_sma and overbought:
        return "BEARISH"
    if above_sma and oversold:
        return "DIP_BUY"
    return "NEUTRAL"
