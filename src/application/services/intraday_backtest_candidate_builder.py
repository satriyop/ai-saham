"""Candidate builder for intraday backtesting candidates.

Computes technical indicators, entry ranges, trend classifications,
and historical broker backing signals to prepare candidate objects.

Layer: Application Service
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.intraday_backtest import IntradayBacktestRequest
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.stats import foreign_vwap_discount_pct
from src.domain.entities.candle import Candle
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass(frozen=True)
class IntradayBacktestCandidate:
    """Carries pre-open signals for one ticker on signal_date."""

    ticker: str
    prev_close: Decimal
    prev_high: Decimal | None
    prev_low: Decimal | None
    atr: Decimal | None
    rsi: Decimal | None
    sma: Decimal | None
    entry_range_low: Decimal | None
    entry_range_high: Decimal | None
    atr_stop: Decimal | None
    trend: str | None
    opening_broker_backing_score: float | None
    opening_broker_backing_tag: str | None
    opening_broker_buy_streak: int | None
    fvwap_discount_pct: float | None


class IntradayBacktestCandidateBuilder:
    """Builds pre-open signals for backtest candidates using only point-in-time historical data."""

    def __init__(
        self,
        *,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        indicator_registry: IndicatorRegistry,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = indicator_registry

    def build(
        self,
        *,
        ticker: str,
        trade_date: date,
        request: IntradayBacktestRequest,
    ) -> IntradayBacktestCandidate | None:
        """Build pre-open signals for ticker using data strictly before trade_date."""
        lookback_start = trade_date - timedelta(days=request.history_days * 2)
        lookback_end = trade_date - timedelta(days=1)

        candles = self._market_repo.get_candles(
            ticker, start_date=lookback_start, end_date=lookback_end,
        )
        if not candles:
            return None

        # Slice to history_days
        if len(candles) > request.history_days:
            candles = candles[-request.history_days:]

        min_required = max(request.atr_period, request.rsi_period, request.sma_period) + 2
        if len(candles) < min_required:
            return None

        prev = candles[-1]
        signal_date = prev.date  # actual last data date (may differ from trade_date-1 on holidays)

        # Compute indicators
        atr_values = self._registry.compute("ATR", candles, request.atr_period)
        rsi_values = self._registry.compute("RSI", candles, request.rsi_period)
        sma_values = self._registry.compute("SMA", candles, request.sma_period)

        atr = atr_values[-1][1] if atr_values else None
        rsi = rsi_values[-1][1] if rsi_values else None
        sma = sma_values[-1][1] if sma_values else None

        # Entry range
        _, range_low, range_high = _compute_entry_range(
            prev.close, atr, request.atr_range_cap_min, request.atr_range_cap_max,
        )

        # ATR stop (anchored on prev.close)
        if atr is not None:
            raw_stop = prev.close - request.atr_multiplier * atr
            floor_stop = prev.close * (Decimal("1") - request.max_stop_pct)
            atr_stop = max(raw_stop, floor_stop).quantize(Decimal("1"))
        else:
            atr_stop = (prev.close * (Decimal("1") - request.max_stop_pct)).quantize(Decimal("1"))

        trend = _classify_trend_backtest(rsi, sma, prev.close, request.rsi_overbought_threshold)

        # Broker signals — use signal_date to avoid lookahead
        broker = _assess_broker_as_of(
            ticker=ticker,
            broker_repo=self._broker_repo,
            candles=candles,
            current_price=prev.close,
            signal_date=signal_date,
            broker_backing_window=request.broker_backing_window_days,
            broker_backing_threshold=request.broker_backing_threshold,
            fvwap_period=request.fvwap_period,
        )

        return IntradayBacktestCandidate(
            ticker=ticker,
            prev_close=prev.close,
            prev_high=prev.high,
            prev_low=prev.low,
            atr=atr,
            rsi=rsi,
            sma=sma,
            entry_range_low=range_low,
            entry_range_high=range_high,
            atr_stop=atr_stop,
            trend=trend,
            opening_broker_backing_score=broker["opening_broker_backing_score"],
            opening_broker_backing_tag=broker["opening_broker_backing_tag"],
            opening_broker_buy_streak=broker["opening_broker_buy_streak"],
            fvwap_discount_pct=broker["fvwap_discount_pct"],
        )


# ── Module Private Helpers ───────────────────────────────────────────────────


def _compute_entry_range(
    prev_close: Decimal,
    atr: Decimal | None,
    cap_min: Decimal,
    cap_max: Decimal,
) -> tuple[Decimal, Decimal | None, Decimal | None]:
    """Compute ATR-scaled entry range. Returns (effective_band, range_low, range_high)."""
    if atr is not None and prev_close > 0:
        atr_pct = atr / prev_close
        effective_band = max(cap_min, min(atr_pct, cap_max))
    else:
        effective_band = cap_max

    if prev_close <= 0:
        return effective_band, None, None

    low = (prev_close * (1 - effective_band)).quantize(Decimal("1"))
    high = (prev_close * (1 + effective_band)).quantize(Decimal("1"))
    return effective_band, low, high


def _classify_trend_backtest(
    rsi: Decimal | None,
    sma: Decimal | None,
    close: Decimal | None,
    overbought: Decimal,
) -> str | None:
    """Trend classifier for backtest context (no gap% available, uses SMA fallback)."""
    if rsi is None:
        return None
    if rsi > overbought:
        return "BEARISH"
    if close is not None and sma is not None:
        above_sma = close > sma
        if Decimal("30") < rsi < Decimal("65") and above_sma:
            return "BULLISH"
        if not above_sma and rsi > Decimal("65"):
            return "BEARISH"
        if above_sma and rsi < Decimal("40"):
            return "DIP_BUY"
    elif Decimal("30") < rsi < Decimal("65"):
        return "BULLISH"
    return "NEUTRAL"


def _assess_broker_as_of(
    ticker: str,
    broker_repo: BrokerDataRepository,
    candles: list[Candle],
    current_price: Decimal | None,
    signal_date: date,
    broker_backing_window: int,
    broker_backing_threshold: float,
    fvwap_period: int,
) -> dict:
    """Compute opening broker-backing tag + Foreign VWAP using data available as of signal_date.

    Critical: uses signal_date (not date.today()) to avoid lookahead bias.
    """
    empty: dict = {
        "opening_broker_backing_score": None,
        "opening_broker_backing_tag": None,
        "opening_broker_buy_streak": None,
        "fvwap_discount_pct": None,
    }
    try:
        start = signal_date - timedelta(days=broker_backing_window + fvwap_period + 10)
        summaries = broker_repo.get_broker_summaries(
            ticker=ticker, start_date=start, end_date=signal_date,
        )
    except Exception:
        return empty

    if not summaries:
        return empty

    result = dict(empty)

    cutoff = signal_date - timedelta(days=broker_backing_window)
    window = [s for s in summaries if s.date > cutoff]

    if window:
        net_buy_days = sum(1 for s in window if s.is_foreign_accumulating)
        total_days = len(window)
        ratio = net_buy_days / total_days if total_days > 0 else 0.0

        streak = 0
        for s in sorted(window, key=lambda x: x.date, reverse=True):
            if s.is_foreign_accumulating:
                streak += 1
            else:
                break

        score = round(ratio * 40.0 + 30.0 * (1.0 - math.exp(-streak / 7.0)), 1)

        if score >= broker_backing_threshold:
            tag = "BACKED"
        elif ratio < 0.3:
            tag = "DISTRIBUTING"
        else:
            tag = "UNCONFIRMED"

        result["opening_broker_backing_score"] = score
        result["opening_broker_backing_tag"] = tag
        result["opening_broker_buy_streak"] = streak

    if candles and current_price is not None and current_price > 0:
        try:
            from plugins.indicators.foreign_vwap import ForeignVWAPIndicator  # type: ignore[import]
            indicator = ForeignVWAPIndicator()
            indicator.set_broker_data(summaries)
            vwap_values = indicator.compute(
                candles[-max(len(candles), fvwap_period):], fvwap_period,
            )
            if vwap_values:
                fvwap = vwap_values[-1]
                if fvwap > 0:
                    result["fvwap_discount_pct"] = foreign_vwap_discount_pct(
                        fvwap,
                        current_price,
                        precision=2,
                    )
        except Exception:
            pass

    return result
