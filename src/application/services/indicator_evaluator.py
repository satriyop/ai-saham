"""IndicatorEvaluator — stateless service mapping a snapshot to IndicatorContext.

Independent of gates and risk levels. Produces a measurement-language
IndicatorContext (BEARISH / NEUTRAL / BULLISH readings) that any consumer —
TechnicalGate, trend display, AI advisor — can read.

Layer: Application
Depends on: Domain value objects only
"""

from src.domain.indicators.indicator_context import IndicatorContext
from src.domain.indicators.indicator_reading import IndicatorReading
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot

_RSI_OVERBOUGHT = 70.0
_RSI_OVERSOLD = 30.0


class IndicatorEvaluator:
    """Map an IndicatorSnapshot to an IndicatorContext using fixed thresholds."""

    def evaluate(self, snapshot: IndicatorSnapshot) -> IndicatorContext:
        # RSI
        rsi_f = float(snapshot.rsi)
        if rsi_f > _RSI_OVERBOUGHT:
            rsi_r = IndicatorReading.BEARISH
            rsi_note = f"RSI {rsi_f:.1f} > {_RSI_OVERBOUGHT} (overbought)"
        elif rsi_f < _RSI_OVERSOLD:
            rsi_r = IndicatorReading.BULLISH
            rsi_note = f"RSI {rsi_f:.1f} < {_RSI_OVERSOLD} (oversold)"
        else:
            rsi_r = IndicatorReading.NEUTRAL
            rsi_note = f"RSI {rsi_f:.1f} neutral"

        # SMA vs EMA relative position — SMA below EMA means price crossed down
        if snapshot.sma < snapshot.ema:
            sma_r = IndicatorReading.BEARISH
            sma_note = f"SMA {float(snapshot.sma):.0f} < EMA {float(snapshot.ema):.0f} (bearish)"
        elif snapshot.sma > snapshot.ema:
            sma_r = IndicatorReading.BULLISH
            sma_note = f"SMA {float(snapshot.sma):.0f} > EMA {float(snapshot.ema):.0f} (bullish)"
        else:
            sma_r = IndicatorReading.NEUTRAL
            sma_note = "SMA = EMA (neutral)"

        # EMA momentum: EMA above SMA = bullish momentum, below = bearish
        if snapshot.ema > snapshot.sma:
            ema_r = IndicatorReading.BULLISH
            ema_note = f"EMA {float(snapshot.ema):.0f} > SMA (bullish momentum)"
        elif snapshot.ema < snapshot.sma:
            ema_r = IndicatorReading.BEARISH
            ema_note = f"EMA {float(snapshot.ema):.0f} < SMA (bearish momentum)"
        else:
            ema_r = IndicatorReading.NEUTRAL
            ema_note = "EMA = SMA (neutral)"

        readings = [sma_r, ema_r, rsi_r]
        bearish_count = readings.count(IndicatorReading.BEARISH)
        bullish_count = readings.count(IndicatorReading.BULLISH)

        if bearish_count >= 2:
            overall = IndicatorReading.BEARISH
        elif bullish_count >= 2:
            overall = IndicatorReading.BULLISH
        else:
            overall = IndicatorReading.NEUTRAL

        all_same = len(set(readings)) == 1
        confidence = 100 if all_same else 50

        return IndicatorContext(
            sma_reading=sma_r,
            ema_reading=ema_r,
            rsi_reading=rsi_r,
            overall=overall,
            confidence=confidence,
            sma_value=snapshot.sma,
            ema_value=snapshot.ema,
            rsi_value=snapshot.rsi,
            rationale=(sma_note, ema_note, rsi_note),
        )
