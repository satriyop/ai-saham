"""Volatility-section serialization for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_label_parsing import _optional_float

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


def _serialize_volatility_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "atr_at_signal": fp.atr_at_signal,
        "atr_pct_at_signal": fp.atr_pct_at_signal,
        "volatility_bucket_at_signal": fp.volatility_bucket_at_signal,
        "volatility_size_multiplier_at_signal": fp.volatility_size_multiplier_at_signal,
    }


def _parse_volatility_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "atr_at_signal": _optional_float(
            data.get("atr_at_signal", data.get("atr_20"))
        ),
        "atr_pct_at_signal": _optional_float(
            data.get("atr_pct_at_signal", data.get("atr_pct"))
        ),
        "volatility_bucket_at_signal": (
            data.get("volatility_bucket_at_signal", data.get("volatility_bucket"))
        ),
        "volatility_size_multiplier_at_signal": _optional_float(
            data.get(
                "volatility_size_multiplier_at_signal",
                data.get("volatility_size_multiplier"),
            )
        ),
    }
