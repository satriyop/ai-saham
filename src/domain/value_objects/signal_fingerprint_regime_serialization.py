"""Regime-section serialization for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_label_parsing import _optional_float, _optional_int

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


def _serialize_regime_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "market_regime": dict(fp.market_regime),
        "market_regime_at_signal": fp.market_regime_at_signal,
        "regime_confidence_at_signal": fp.regime_confidence_at_signal,
        "regime_stability_at_signal": fp.regime_stability_at_signal,
        "days_in_regime_at_signal": fp.days_in_regime_at_signal,
        "regime_transition_warning_at_signal": fp.regime_transition_warning_at_signal,
        "regime_detection_method_at_signal": fp.regime_detection_method_at_signal,
        "coverage": fp.coverage,
        "conviction": fp.conviction,
    }


def _parse_regime_fields(data: dict[str, Any]) -> dict[str, Any]:
    regime = data.get("market_regime")
    if regime is None and data.get("market_regime_at_signal") is not None:
        regime = {
            "regime": data.get("market_regime_at_signal"),
            "regime_confidence": data.get("regime_confidence_at_signal"),
            "regime_stability": data.get("regime_stability_at_signal"),
        }
        if data.get("decision_constraints") is not None:
            regime["decision_constraints"] = data.get("decision_constraints")

    return {
        "market_regime": dict(regime or {}),
        "market_regime_at_signal": (
            data.get("market_regime_at_signal")
            or (regime.get("regime") if regime else None)
        ),
        "regime_confidence_at_signal": _optional_float(
            data.get("regime_confidence_at_signal")
            if data.get("regime_confidence_at_signal") is not None
            else (regime.get("regime_confidence") if regime else None)
        ),
        "regime_stability_at_signal": (
            data.get("regime_stability_at_signal")
            or (regime.get("regime_stability") if regime else None)
        ),
        "days_in_regime_at_signal": _optional_int(
            data.get("days_in_regime_at_signal")
            if data.get("days_in_regime_at_signal") is not None
            else (regime.get("days_in_regime") if regime else None)
        ),
        "regime_transition_warning_at_signal": (
            data.get("regime_transition_warning_at_signal")
            or (regime.get("transition_warning") if regime else None)
        ),
        "regime_detection_method_at_signal": data.get("regime_detection_method_at_signal"),
        "coverage": _optional_float(data.get("coverage", data.get("coverage_score"))),
        "conviction": _optional_float(data.get("conviction", data.get("conviction_score"))),
    }
