"""
Build pre-open technical context: ATR, RSI, SMA, previous OHLC + candles.

Layer: Application
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.domain.ports.market_data_repository import MarketDataRepository


def build_pre_open_technical_context(
    repository: "MarketDataRepository",
    registry: "IndicatorRegistry",
    ticker: str,
    sma_period: int = 20,
    rsi_period: int = 14,
    atr_period: int = 14,
    history_days: int = 365,
) -> dict:
    """Load candles and compute ATR, RSI, SMA, prev OHLC.

    Returns dict with keys: prev_close, prev_high, prev_low, rsi, sma, atr,
    candles (list), warning. All indicator values default to None on failure.
    """
    empty = {
        "prev_close": None,
        "prev_high": None,
        "prev_low": None,
        "rsi": None,
        "sma": None,
        "atr": None,
        "candles": [],
        "warning": None,
    }

    try:
        candles = repository.get_candles(ticker.upper())
        if not candles:
            empty["warning"] = (
                f"{ticker}: No cached data - run 'saham fetch market {ticker} --days 365' first"
            )
            return empty

        if len(candles) > history_days:
            candles = candles[-history_days:]

        prev = candles[-1]

        sma_values = registry.compute("SMA", candles, sma_period)
        rsi_values = registry.compute("RSI", candles, rsi_period)
        atr_values = registry.compute("ATR", candles, atr_period)

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
