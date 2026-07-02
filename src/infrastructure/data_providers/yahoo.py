"""
Yahoo Finance market data provider.

This adapter implements MarketDataProvider using yfinance.
IDX tickers automatically get .JK suffix appended.

Layer: Infrastructure
Depends on: Domain ports, yfinance (external library)
"""

from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf

from src.domain.value_objects.benchmark_symbol import (
    CANONICAL_BENCHMARK_TICKER,
    YAHOO_IHSG_TICKER,
    is_benchmark_ticker,
)
from src.domain.value_objects import is_non_idx_ticker
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import (
    MarketDataProvider,
    MarketDataProviderError,
)

# Yahoo Finance reports ^JKSE (IHSG) volume in lots, not shares.
# All other IDX infrastructure (Stockbit, storage) uses shares (lots * 100).
_LOTS_TO_SHARES = 100


class YahooFinanceProvider(MarketDataProvider):
    """
    Market data provider using Yahoo Finance (yfinance).

    This provider:
    - Auto-appends .JK suffix for IDX tickers
    - Normalizes data to Candle entities
    - Handles yfinance errors gracefully

    Configuration:
        market_suffix: Suffix to append (default: '.JK' for IDX)
    """

    def __init__(
        self,
        market_suffix: str | None = None,
        non_idx_tickers: set[str] | None = None,
    ) -> None:
        """
        Initialize Yahoo Finance provider.

        Args:
            market_suffix: Suffix for ticker symbols (e.g., '.JK' for IDX)
            non_idx_tickers: Extra global tickers to skip suffix appending.
        """
        if market_suffix is None:
            from src.infrastructure.config.app_config import APP_CFG
            market_suffix = APP_CFG.market.suffix
        self._market_suffix = market_suffix
        self._non_idx_tickers = non_idx_tickers or set()
        self.provider_name = "yahoo"
        self.volume_unit = "shares"
        self.price_adjustment_policy = "yfinance_default"

    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        """
        Fetch daily OHLCV data from Yahoo Finance.

        Args:
            ticker: Stock ticker (e.g., 'BBCA' - suffix added automatically)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of Candle entities sorted by date ascending.

        Raises:
            MarketDataProviderError: If fetch fails.
        """
        yahoo_ticker = self._to_yahoo_ticker(ticker)

        try:
            # yfinance end_date is exclusive, so add 1 day
            yf_end = end_date + timedelta(days=1)

            stock = yf.Ticker(yahoo_ticker)
            df = stock.history(
                start=start_date.isoformat(),
                end=yf_end.isoformat(),
                interval="1d",
            )

            if df.empty:
                return []

            return self._dataframe_to_candles(ticker.upper(), df)

        except Exception as e:
            raise MarketDataProviderError(f"Failed to fetch data for {ticker}: {e}") from e

    def _to_yahoo_ticker(self, ticker: str) -> str:
        """Convert ticker to Yahoo Finance format."""
        ticker = ticker.upper().strip()
        if ticker == CANONICAL_BENCHMARK_TICKER:
            return YAHOO_IHSG_TICKER
        if is_non_idx_ticker(ticker, self._non_idx_tickers):
            return ticker
        if "." in ticker:
            return ticker
        if not ticker.endswith(self._market_suffix):
            return f"{ticker}{self._market_suffix}"
        return ticker

    def _dataframe_to_candles(self, ticker: str, df) -> list[Candle]:
        """Convert yfinance DataFrame to list of Candle entities.

        Volume note for IHSG (^JKSE):
        Yahoo Finance reports ^JKSE volume in lots, not shares. We multiply
        by 100 so the stored value is in shares — consistent with Stockbit.
        Rows where Yahoo returns volume=0 for the benchmark are skipped;
        this happens for in-progress intraday sessions and is not a valid
        daily candle.
        """
        is_benchmark = is_benchmark_ticker(ticker)
        candles = []

        for idx, row in df.iterrows():
            try:
                raw_volume = int(row["Volume"])

                # Yahoo returns volume=0 for ^JKSE during an in-progress
                # session. A zero-volume IHSG candle is not meaningful as a
                # settled daily bar — skip it so stale data is not overwritten.
                if is_benchmark and raw_volume == 0:
                    continue

                # Yahoo reports ^JKSE volume in lots; convert to shares.
                volume = raw_volume * _LOTS_TO_SHARES if is_benchmark else raw_volume

                candle = Candle(
                    ticker=ticker,
                    date=idx.date(),
                    open=Decimal(str(row["Open"])).quantize(Decimal("0.01")),
                    high=Decimal(str(row["High"])).quantize(Decimal("0.01")),
                    low=Decimal(str(row["Low"])).quantize(Decimal("0.01")),
                    close=Decimal(str(row["Close"])).quantize(Decimal("0.01")),
                    volume=volume,
                )
                candles.append(candle)
            except (ValueError, KeyError):
                # Skip invalid rows but log them
                continue

        # Sort by date ascending
        candles.sort(key=lambda c: c.date)
        return candles
