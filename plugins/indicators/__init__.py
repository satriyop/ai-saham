"""
Indicator plugins directory.

Drop .py files here implementing IndicatorPlugin to extend the engine.
Files starting with _ are ignored.
"""

from plugins.indicators.bollinger_bands import (
    BollingerLowerIndicator,
    BollingerUpperIndicator,
    BollingerWidthIndicator,
    BollingerWidthT1Indicator,
)
from plugins.indicators.donchian_channel import (
    DonchianLowerIndicator,
    DonchianMiddleIndicator,
    DonchianUpperIndicator,
)
from plugins.indicators.foreign_vwap import ForeignVWAPIndicator
from plugins.indicators.ichimoku import (
    IchimokuChikou,
    IchimokuKijun,
    IchimokuSpanA,
    IchimokuSpanB,
    IchimokuTenkan,
)
from plugins.indicators.macd import MACDIndicator, MACDSignalIndicator
from plugins.indicators.mfi import MoneyFlowIndexIndicator
from plugins.indicators.obv import OnBalanceVolumeIndicator
from plugins.indicators.relative_strength import RelativeStrengthIHSGIndicator
from plugins.indicators.stochastic import StochasticIndicator
from plugins.indicators.volume_ratio import VolumeRatioIndicator
from plugins.indicators.williams_r import WilliamsRIndicator

__all__ = [
    "MACDIndicator",
    "MACDSignalIndicator",
    "BollingerUpperIndicator",
    "BollingerLowerIndicator",
    "BollingerWidthIndicator",
    "BollingerWidthT1Indicator",
    "DonchianUpperIndicator",
    "DonchianLowerIndicator",
    "DonchianMiddleIndicator",
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
