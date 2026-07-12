from datetime import date
from decimal import Decimal

from src.domain.entities.candle import Candle


def make_candle(
    ticker: str = "BBCA",
    candle_date: date = date(2024, 1, 1),
    close: Decimal = Decimal("1000"),
) -> Candle:
    """Create a test candle with sensible defaults."""
    return Candle(
        ticker=ticker,
        date=candle_date,
        open=close,
        high=close + Decimal("10"),
        low=close - Decimal("10"),
        close=close,
        volume=100000,
    )


def make_candles(
    ticker: str = "BBCA",
    count: int = 10,
    start_price: Decimal = Decimal("1000"),
    price_increment: Decimal = Decimal("10"),
) -> list[Candle]:
    """Create a list of test candles with incrementing prices."""
    candles = []
    for i in range(count):
        price = start_price + (price_increment * i)
        candles.append(
            make_candle(
                ticker=ticker,
                candle_date=date(2024, 1, i + 1),
                close=price,
            )
        )
    return candles
