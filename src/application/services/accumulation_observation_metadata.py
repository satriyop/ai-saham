"""Market context and volatility fingerprint serialization for observation payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.services.volatility_context import VolatilityContext
    from src.domain.value_objects.market_context import MarketContext


def _market_context_fingerprint(market_context: "MarketContext | None") -> dict:
    return {
        "regime_confidence_at_signal": (
            market_context.regime_confidence if market_context is not None else None
        ),
        "regime_stability_at_signal": (
            market_context.regime_stability if market_context is not None else None
        ),
        "days_in_regime_at_signal": (
            market_context.days_in_regime if market_context is not None else None
        ),
        "regime_transition_warning_at_signal": (
            market_context.transition_warning if market_context is not None else None
        ),
        "regime_detection_method_at_signal": None,
    }


def _volatility_fingerprint(vc: "VolatilityContext | None") -> dict:
    if vc is None:
        return {
            "atr_at_signal": None,
            "atr_pct_at_signal": None,
            "volatility_bucket_at_signal": None,
            "volatility_size_multiplier_at_signal": None,
        }
    return {
        "atr_at_signal": vc.atr_at_signal,
        "atr_pct_at_signal": vc.atr_pct_at_signal,
        "volatility_bucket_at_signal": vc.volatility_bucket_at_signal,
        "volatility_size_multiplier_at_signal": vc.volatility_size_multiplier_at_signal,
    }
