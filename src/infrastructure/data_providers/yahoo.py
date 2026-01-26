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

from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import (
    MarketDataProvider,
    MarketDataProviderError,
)


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

    def __init__(self, market_suffix: str = ".JK") -> None:
        """
        Initialize Yahoo Finance provider.

        Args:
            market_suffix: Suffix for ticker symbols (e.g., '.JK' for IDX)
        """
        self._market_suffix = market_suffix

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
            raise MarketDataProviderError(
                f"Failed to fetch data for {ticker}: {e}"
            ) from e

    def _to_yahoo_ticker(self, ticker: str) -> str:
        """Convert ticker to Yahoo Finance format."""
        ticker = ticker.upper().strip()
        if not ticker.endswith(self._market_suffix):
            return f"{ticker}{self._market_suffix}"
        return ticker

    def _dataframe_to_candles(self, ticker: str, df) -> list[Candle]:
        """Convert yfinance DataFrame to list of Candle entities."""
        candles = []

        for idx, row in df.iterrows():
            try:
                candle = Candle(
                    ticker=ticker,
                    date=idx.date(),
                    open=Decimal(str(row["Open"])).quantize(Decimal("0.01")),
                    high=Decimal(str(row["High"])).quantize(Decimal("0.01")),
                    low=Decimal(str(row["Low"])).quantize(Decimal("0.01")),
                    close=Decimal(str(row["Close"])).quantize(Decimal("0.01")),
                    volume=int(row["Volume"]),
                )
                candles.append(candle)
            except (ValueError, KeyError):
                # Skip invalid rows but log them
                continue

        # Sort by date ascending
        candles.sort(key=lambda c: c.date)
        return candles
