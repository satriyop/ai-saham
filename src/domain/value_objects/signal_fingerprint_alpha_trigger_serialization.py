"""Alpha/trigger-section serialization for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_label_parsing import _optional_bool, _optional_float

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


def _serialize_alpha_trigger_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "alpha_score": fp.alpha_score,
        "trigger_score": fp.trigger_score,
        "alpha_trigger_final_exact_score": fp.alpha_trigger_final_exact_score,
        "alpha_trigger_horizon": fp.alpha_trigger_horizon,
        "alpha_trigger_alpha_weight": fp.alpha_trigger_alpha_weight,
        "flow_trigger_allowed": fp.flow_trigger_allowed,
        "alpha_trigger_route_metadata": [dict(v) for v in fp.alpha_trigger_route_metadata],
        "alpha_trigger_unavailable_reasons": list(fp.alpha_trigger_unavailable_reasons),
    }


def _parse_alpha_trigger_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "alpha_score": _optional_float(data.get("alpha_score")),
        "trigger_score": _optional_float(data.get("trigger_score")),
        "alpha_trigger_final_exact_score": _optional_float(
            data.get("alpha_trigger_final_exact_score")
        ),
        "alpha_trigger_horizon": data.get("alpha_trigger_horizon"),
        "alpha_trigger_alpha_weight": _optional_float(data.get("alpha_trigger_alpha_weight")),
        "flow_trigger_allowed": _optional_bool(data.get("flow_trigger_allowed")),
        "alpha_trigger_route_metadata": tuple(
            dict(v) for v in data.get("alpha_trigger_route_metadata") or () if isinstance(v, dict)
        ),
        "alpha_trigger_unavailable_reasons": tuple(
            str(v) for v in data.get("alpha_trigger_unavailable_reasons") or ()
        ),
    }
