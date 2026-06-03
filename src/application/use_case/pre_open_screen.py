"""
PreOpenScreenUseCase — orchestrates the 7-step pre-open screening workflow.

Steps:
  1-3. Fetch movers from Stockbit browser, filter by IEV >= threshold
  4.   AI research: technical indicators + news sentiment per ticker
  5.   Build ScreenerCandidate list
  6.   Fetch order book best bid → compute entry price (bid + N ticks)
  7.   Compute stop-loss (entry * (1 - stop_loss_pct))

Layer: Application
Mode: AI Mode ON (requires browser provider + AI explainer)
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
from src.infrastructure.browser.stockbit_browser import entry_price_from_bid


@dataclass
class PreOpenScreenConfig:
    """Screening parameters, loaded from strategy.yaml or overridden by CLI flags.

    Attributes:
        iev_min: Minimum IEV to qualify
        capital: Entry position size in IDR
        tick_above: Number of IDX ticks above best bid for entry price
        stop_loss_pct: Fraction below entry to place hard stop (0.20 = 20%)
        sma_period: SMA lookback for trend assessment
        rsi_period: RSI lookback for momentum assessment
        history_days: Days of market data to load for indicator calculation
    """

    iev_min: int = 100_000
    capital: Decimal = Decimal("3000000")
    tick_above: int = 1
    stop_loss_pct: Decimal = Decimal("0.20")
    sma_period: int = 20
    rsi_period: int = 14
    history_days: int = 365

    @classmethod
    def from_yaml(cls, data: dict) -> "PreOpenScreenConfig":
        """Parse from strategy.yaml content dict."""
        screener = data.get("screener", {})
        entry = data.get("entry", {})
        risk = data.get("risk", {})
        analysis = data.get("analysis", {})

        return cls(
            iev_min=int(screener.get("iev_min", 100_000)),
            capital=Decimal(str(entry.get("capital", 3_000_000))),
            tick_above=int(entry.get("tick_above", 1)),
            stop_loss_pct=Decimal(str(risk.get("stop_loss_pct", 0.20))),
            sma_period=int(analysis.get("sma_period", 20)),
            rsi_period=int(analysis.get("rsi_period", 14)),
            history_days=int(analysis.get("days", 365)),
        )


@dataclass
class PreOpenScreenRequest:
    """Input to the use case.

    Attributes:
        config: Screening parameters
        run_date: Date for the screen (default: today)
    """

    config: PreOpenScreenConfig
    run_date: date | None = None


@dataclass
class PreOpenScreenResponse:
    """Output of the use case.

    Attributes:
        result: The screening result with all candidates
        warnings: Non-fatal issues encountered during the run
    """

    result: PreOpenScreenResult
    warnings: list[str]


class PreOpenScreenUseCase:
    """Orchestrates the pre-open screening workflow.

    Dependencies:
        browser: Provides movers list and order book data (requires browser session)
        repository: Local SQLite market data cache for technical indicators
        registry: Indicator registry for SMA / RSI computation
        ai_explainer: Optional — generates AI research summary per ticker

    Usage:
        config = PreOpenScreenConfig(iev_min=100_000, capital=Decimal("3000000"))
        use_case = PreOpenScreenUseCase(browser=provider, repository=repo, registry=reg)
        response = use_case.execute(PreOpenScreenRequest(config=config))
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
        """Run the 7-step pre-open screening workflow.

        Args:
            request: Screening config and run date

        Returns:
            Response with screened candidates and any warnings encountered

        Raises:
            BrowserInteractionRequired: Propagated from browser provider when
                no pre-fetched data was supplied
        """
        config = request.config
        run_date = request.run_date or date.today()
        warnings: list[str] = []

        # Steps 1-3: Fetch movers, filter by IEV threshold
        raw_movers = self._browser.fetch_preopen_movers(config.iev_min)
        total_seen = len(raw_movers)

        candidates: list[ScreenerCandidate] = []

        for mover in raw_movers:
            ticker = mover.ticker

            # Step 4: Technical analysis (from cached market data)
            trend_signal, rsi_val, sma_val, tech_warning = self._assess_technicals(
                ticker=ticker,
                sma_period=config.sma_period,
                rsi_period=config.rsi_period,
                history_days=config.history_days,
            )
            if tech_warning:
                warnings.append(tech_warning)

            # Step 4 (AI): Research summary per ticker
            ai_summary = self._research_ticker(ticker)

            # Step 6: Order book → entry price
            entry_price: Decimal | None = None
            stop_loss_price: Decimal | None = None
            ob = self._browser.fetch_order_book_best_bid(ticker)
            if ob is not None:
                entry_price = entry_price_from_bid(ob.price, config.tick_above)
                stop_loss_price = (entry_price * (1 - config.stop_loss_pct)).quantize(
                    Decimal("1")
                )
            else:
                warnings.append(
                    f"{ticker}: No order book data — entry/stop-loss not computed"
                )

            # Step 5 + 7: Build candidate
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

    def _assess_technicals(
        self,
        ticker: str,
        sma_period: int,
        rsi_period: int,
        history_days: int,
    ) -> tuple[str | None, Decimal | None, Decimal | None, str | None]:
        """Compute SMA and RSI, return (trend_signal, rsi, sma, warning)."""
        try:
            candles = self._repository.get_candles(ticker.upper())
            if not candles:
                return None, None, None, f"{ticker}: No cached data — run 'saham fetch {ticker}' first"

            if len(candles) > history_days:
                candles = candles[-history_days:]

            sma_values = self._registry.compute("SMA", candles, sma_period)
            rsi_values = self._registry.compute("RSI", candles, rsi_period)

            sma_val = sma_values[-1][1] if sma_values else None
            rsi_val = rsi_values[-1][1] if rsi_values else None
            latest_close = candles[-1].close if candles else None

            trend_signal = self._classify_trend(latest_close, sma_val, rsi_val)
            return trend_signal, rsi_val, sma_val, None

        except Exception as e:
            return None, None, None, f"{ticker}: Technical analysis failed — {e}"

    @staticmethod
    def _classify_trend(
        close: Decimal | None,
        sma: Decimal | None,
        rsi: Decimal | None,
    ) -> str | None:
        """Simple 3-tier trend signal from close vs SMA and RSI."""
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

    def _research_ticker(self, ticker: str) -> str | None:
        """Generate AI research summary for a ticker (optional step)."""
        if self._ai_explainer is None:
            return None
        try:
            return self._ai_explainer.research(ticker)
        except Exception:
            return None
