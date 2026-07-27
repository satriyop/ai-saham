"""
Market context regime confidence and detection-fingerprint inputs.

Pure functions, no persistence or repository access. Used by
BuildMarketContextUseCase to populate BuildMarketContextResponse.regime_detection_inputs.

Layer: Application
"""

from __future__ import annotations

from src.application.services.market_context_factor_scorers import pct_return, simple_moving_average
from src.domain.value_objects.market_context import MarketRegime


def compute_regime_confidence(
    *,
    regime: MarketRegime,
    conviction: float,
    vix_value,
    thresholds,
) -> float:
    """
    Compute regime confidence (0.0–1.0) as the conviction margin from the nearest
    regime boundary, normalized to a [0, 1] range.

    VOLATILE confidence is based on VIX distance from the hard threshold.
    """
    risk_on_min = thresholds.risk_on_min_score
    risk_off_max = thresholds.risk_off_max_score
    # half of the neutral band (risk_off_max ... risk_on_min)
    boundary_half = (risk_on_min - risk_off_max) / 2.0

    if boundary_half <= 0:
        return 0.5

    if regime == MarketRegime.VOLATILE:
        if vix_value is not None:
            vix_v = float(vix_value)
            vt = thresholds.volatile_vix_override
            if vt > 0:
                margin = max(0.0, vix_v - vt) / vt
                return min(1.0, round(margin, 4))
        return 0.8  # hard threshold fired — treat as high confidence

    if regime == MarketRegime.RISK_ON:
        margin = conviction - risk_on_min
    elif regime == MarketRegime.RISK_OFF:
        margin = risk_off_max - conviction
    else:  # NEUTRAL
        margin = min(conviction - risk_off_max, risk_on_min - conviction)

    return min(1.0, max(0.0, round(margin / boundary_half, 4)))


def compute_market_context_detection_inputs(
    *,
    ihsg_candles: list,
    foreign_flow_series: list[tuple],
    idx_breadth_pct: float | None,
    banking_universe: list[str],
    universe_candles: dict[str, list],
) -> dict[str, object]:
    breadth_pct = idx_breadth_pct
    return {
        **_compute_ihsg_inputs(ihsg_candles),
        **_compute_foreign_flow_inputs(foreign_flow_series),
        "ihsg_breadth_pct_above_ma": round(breadth_pct, 4) if breadth_pct is not None else None,
        "sector_breadth": round(breadth_pct, 4) if breadth_pct is not None else None,
        "banking_sector_vs_ihsg": _compute_banking_vs_ihsg(
            banking_universe, universe_candles, ihsg_candles
        ),
    }


def _compute_ihsg_inputs(candles: list) -> dict:
    """
    Compute IHSG-based detection inputs from raw candle history.

    Returns a dict with keys: ihsg_20d_return, ihsg_trend_structure,
    ihsg_volume_trend, ihsg_atr_pct.  All values are float | None.
    """
    if not candles or len(candles) < 2:
        return {
            "ihsg_20d_return": None,
            "ihsg_trend_structure": None,
            "ihsg_volume_trend": None,
            "ihsg_atr_pct": None,
        }

    ihsg_20d_return = pct_return(candles, 20)

    # Trend structure: close vs SMA20 vs SMA50
    close = float(candles[-1].close)
    sma20 = simple_moving_average(candles, 20)
    sma50 = simple_moving_average(candles, 50)

    if sma50 is not None and sma20 is not None:
        above_50 = close >= float(sma50)
        above_20 = close >= float(sma20)
        if above_50 and above_20:
            trend_structure = "ABOVE_BOTH"
        elif above_20 and not above_50:
            trend_structure = "ABOVE_FAST_ONLY"
        else:
            trend_structure = "BELOW_BOTH"
    elif sma20 is not None:
        trend_structure = "ABOVE_FAST_ONLY" if close >= float(sma20) else "BELOW_FAST_ONLY"
    else:
        trend_structure = "UNKNOWN"

    # Volume trend: recent 5d avg vol / 20d avg vol
    volume_trend: float | None = None
    volumes = [
        float(c.volume)
        for c in candles
        if hasattr(c, "volume") and c.volume is not None and float(c.volume) > 0
    ]
    if len(volumes) >= 20:
        recent_vol = sum(volumes[-5:]) / min(5, len(volumes[-5:]))
        avg_vol = sum(volumes[-20:]) / 20
        if avg_vol > 0:
            volume_trend = round(recent_vol / avg_vol, 4)

    # IHSG ATR% (14d): average true range / close * 100
    atr_pct: float | None = None
    atr_period = 14
    if len(candles) >= atr_period + 1:
        trs = []
        for i in range(-atr_period, 0):
            c_curr = candles[i]
            c_prev = candles[i - 1]
            has_high = hasattr(c_curr, "high") and c_curr.high
            has_low = hasattr(c_curr, "low") and c_curr.low
            high = float(c_curr.high) if has_high else float(c_curr.close)
            low = float(c_curr.low) if has_low else float(c_curr.close)
            prev_c = float(c_prev.close)
            tr = max(high - low, abs(high - prev_c), abs(low - prev_c))
            trs.append(tr)
        if trs and close > 0:
            atr_pct = round(sum(trs) / len(trs) / close * 100, 4)

    return {
        "ihsg_20d_return": round(ihsg_20d_return, 4) if ihsg_20d_return is not None else None,
        "ihsg_trend_structure": trend_structure,
        "ihsg_volume_trend": volume_trend,
        "ihsg_atr_pct": atr_pct,
    }


def _compute_foreign_flow_inputs(series: list[tuple]) -> dict:
    """
    Derive diagnostic foreign-flow fingerprint inputs from the aggregated series.

    Returns idx_foreign_flow_5d, idx_foreign_flow_20d, foreign_buy_streak,
    foreign_sell_streak.  All values are float | int | None.
    """
    if not series:
        return {
            "idx_foreign_flow_5d": None,
            "idx_foreign_flow_20d": None,
            "foreign_buy_streak": None,
            "foreign_sell_streak": None,
        }

    sorted_series = sorted(series, key=lambda x: x[0])
    values = [float(v) for _, v in sorted_series]

    last_5 = values[-5:] if len(values) >= 5 else values
    last_20 = values[-20:] if len(values) >= 20 else values

    # Count consecutive tail days with same sign (buy or sell streak)
    buy_streak = 0
    sell_streak = 0
    for v in reversed(values):
        if v > 0:
            if sell_streak > 0:
                break
            buy_streak += 1
        elif v < 0:
            if buy_streak > 0:
                break
            sell_streak += 1
        else:
            break

    return {
        "idx_foreign_flow_5d": round(sum(last_5), 2) if last_5 else None,
        "idx_foreign_flow_20d": round(sum(last_20), 2) if last_20 else None,
        "foreign_buy_streak": buy_streak if buy_streak > 0 else 0,
        "foreign_sell_streak": sell_streak if sell_streak > 0 else 0,
    }


def _compute_banking_vs_ihsg(
    banking_universe: list[str],
    universe_candles: dict[str, list],
    ihsg_candles: list,
    lookback: int = 20,
) -> float | None:
    """
    Equal-weight banking-sector 20d return minus IHSG 20d return.

    Returns None when banking_universe is empty or tickers lack sufficient history.
    """
    if not banking_universe or not universe_candles or not ihsg_candles:
        return None

    ihsg_ret = pct_return(ihsg_candles, lookback)
    if ihsg_ret is None:
        return None

    returns = []
    for ticker in banking_universe:
        candles = universe_candles.get(ticker.upper())
        if not candles:
            continue
        ret = pct_return(candles, lookback)
        if ret is not None:
            returns.append(ret)

    if not returns:
        return None

    banking_ret = sum(returns) / len(returns)
    return round(banking_ret - ihsg_ret, 4)
