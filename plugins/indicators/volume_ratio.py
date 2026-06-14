"""
Volume Ratio (VR) indicator plugin.

Measures current volume relative to the N-day average of prior sessions.
A key indicator for the IDX market where institutional accumulation is
reliably detected through abnormal volume spikes.

VR = Volume[today] / Average(Volume[today-N .. today-1])

Interpretation:
  VR > 2.0 : abnormally high volume — possible institutional activity
  VR > 3.0 : very high volume — strong conviction move
  VR < 0.5 : low volume — weak/unconvincing move
  VR = 1.0 : exactly average volume

Usage in rules:
  left: { indicator: vol_ratio }
  operator: ">"
  right: { value: 2.0 }
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle


class VolumeRatioIndicator(IndicatorPlugin):
    """Volume Ratio: current volume vs N-day prior average."""

    name = "VOLUME_RATIO"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Compute volume ratio for each candle.

        Args:
            candles: Price data sorted by date ascending
            period: Lookback window for average volume (previous sessions only)

        Returns:
            List of VR values. Length = len(candles) - period.
            First value aligns to candles[period] (first candle with full window).
        """
        if len(candles) <= period:
            return []

        result: list[Decimal] = []

        for i in range(period, len(candles)):
            prior_volumes = [c.volume for c in candles[i - period:i]]
            avg_vol = sum(prior_volumes) / period

            if avg_vol == 0:
                result.append(Decimal("1"))
            else:
                ratio = Decimal(str(candles[i].volume)) / Decimal(str(avg_vol))
                result.append(ratio.quantize(Decimal("0.01")))

        return result
