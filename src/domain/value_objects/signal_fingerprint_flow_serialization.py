"""Flow-section serialization for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_label_parsing import _optional_bool, _optional_float

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


def _serialize_flow_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "rsi": fp.rsi,
        "bb_width_pctile": fp.bb_width_pctile,
        "vwap_position": fp.vwap_position,
        "volume_ratio": fp.volume_ratio,
        "volume_dry_up_ratio": fp.volume_dry_up_ratio,
        "volume_expansion_ratio": fp.volume_expansion_ratio,
        "volume_dry_up_confirmed": fp.volume_dry_up_confirmed,
        "volume_expansion_confirmed": fp.volume_expansion_confirmed,
        "volume_trigger_confirmed": fp.volume_trigger_confirmed,
        "cnfb": fp.cnfb,
        "foreign_participation": fp.foreign_participation,
        "foreign_concentration": fp.foreign_concentration,
        "domestic_broker_accumulation": fp.domestic_broker_accumulation,
    }


def _parse_flow_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "rsi": _optional_float(data.get("rsi", data.get("rsi_at_signal"))),
        "bb_width_pctile": _optional_float(
            data.get("bb_width_pctile", data.get("bb_width_pctile_at_signal"))
        ),
        "vwap_position": _optional_float(
            data.get("vwap_position", data.get("vwap_position_at_signal"))
        ),
        "volume_ratio": _optional_float(
            data.get("volume_ratio", data.get("volume_ratio_at_signal"))
        ),
        "volume_dry_up_ratio": _optional_float(
            data.get("volume_dry_up_ratio", data.get("volume_dry_up_ratio_at_signal"))
        ),
        "volume_expansion_ratio": _optional_float(
            data.get("volume_expansion_ratio", data.get("volume_expansion_ratio_at_signal"))
        ),
        "volume_dry_up_confirmed": _optional_bool(data.get("volume_dry_up_confirmed")),
        "volume_expansion_confirmed": _optional_bool(data.get("volume_expansion_confirmed")),
        "volume_trigger_confirmed": _optional_bool(data.get("volume_trigger_confirmed")),
        "cnfb": _optional_float(data.get("cnfb", data.get("cnfb_20d_at_signal"))),
        "foreign_participation": _optional_float(
            data.get(
                "foreign_participation",
                data.get("foreign_participation_at_signal"),
            )
        ),
        "foreign_concentration": _optional_float(
            data.get(
                "foreign_concentration",
                data.get("foreign_concentration_at_signal"),
            )
        ),
        "domestic_broker_accumulation": _optional_float(
            data.get(
                "domestic_broker_accumulation",
                data.get("domestic_broker_accumulation_at_signal"),
            )
        ),
    }
