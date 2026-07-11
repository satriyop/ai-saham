"""ATR computation helper for swing analysis workflow.

Layer: Application
"""

from decimal import Decimal
from typing import Any


def compute_swing_atr(registry: Any, candles: list[Any], period: int = 14) -> Decimal | None:
    try:
        atr_values = registry.compute("ATR", candles, period)
        if atr_values:
            return atr_values[-1][1]
    except Exception:
        return None
    return None
