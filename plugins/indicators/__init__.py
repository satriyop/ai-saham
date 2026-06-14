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
from plugins.indicators.volume_ratio import VolumeRatioIndicator
from plugins.indicators.mfi import MoneyFlowIndexIndicator
from plugins.indicators.obv import OnBalanceVolumeIndicator
from plugins.indicators.williams_r import WilliamsRIndicator
from plugins.indicators.relative_strength import RelativeStrengthIHSGIndicator

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
    "VolumeRatioIndicator",
    "MoneyFlowIndexIndicator",
    "OnBalanceVolumeIndicator",
    "WilliamsRIndicator",
    "RelativeStrengthIHSGIndicator",
]
