"""
Indicator plugins directory.

Drop .py files here implementing IndicatorPlugin to extend the engine.
Files starting with _ are ignored.
"""

from plugins.indicators.macd import MACDIndicator, MACDSignalIndicator
from plugins.indicators.bollinger_bands import (
    BollingerUpperIndicator,
    BollingerLowerIndicator,
    BollingerWidthIndicator,
)
from plugins.indicators.stochastic import StochasticIndicator
from plugins.indicators.foreign_vwap import ForeignVWAPIndicator
from plugins.indicators.ichimoku import (
    IchimokuTenkan,
    IchimokuKijun,
    IchimokuSpanA,
    IchimokuSpanB,
    IchimokuChikou,
)

__all__ = [
    "MACDIndicator",
    "MACDSignalIndicator",
    "BollingerUpperIndicator",
    "BollingerLowerIndicator",
    "BollingerWidthIndicator",
    "StochasticIndicator",
    "ForeignVWAPIndicator",
    "IchimokuTenkan",
    "IchimokuKijun",
    "IchimokuSpanA",
    "IchimokuSpanB",
    "IchimokuChikou",
]
