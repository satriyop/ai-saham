"""Serialization and parsing logic for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_fingerprint_alpha_trigger_serialization import (
    _parse_alpha_trigger_fields,
    _serialize_alpha_trigger_fields,
)
from src.domain.value_objects.signal_fingerprint_context_serialization import (
    _parse_company_quality_fields,
    _parse_institutional_accumulation_fields,
    _parse_sector_context_fields,
    _parse_ticker_profile_fields,
    _serialize_company_quality_fields,
    _serialize_institutional_accumulation_fields,
    _serialize_sector_context_fields,
    _serialize_ticker_profile_fields,
)
from src.domain.value_objects.signal_fingerprint_flow_serialization import (
    _parse_flow_fields,
    _serialize_flow_fields,
)
from src.domain.value_objects.signal_fingerprint_regime_serialization import (
    _parse_regime_fields,
    _serialize_regime_fields,
)
from src.domain.value_objects.signal_fingerprint_setup_serialization import (
    _parse_setup_fields,
    _serialize_setup_fields,
)
from src.domain.value_objects.signal_fingerprint_strategy_serialization import (
    _parse_strategy_fields,
    _serialize_strategy_fields,
)
from src.domain.value_objects.signal_fingerprint_volatility_serialization import (
    _parse_volatility_fields,
    _serialize_volatility_fields,
)

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


def signal_observation_fingerprint_to_dict(
    fingerprint: "SignalObservationFingerprint",
) -> dict[str, Any]:
    """Serialize a SignalObservationFingerprint to a flat dictionary."""
    data = {}
    data.update(_serialize_setup_fields(fingerprint))
    data.update(_serialize_strategy_fields(fingerprint))
    data.update(_serialize_flow_fields(fingerprint))
    data.update(_serialize_regime_fields(fingerprint))
    data.update(_serialize_institutional_accumulation_fields(fingerprint))
    data.update(_serialize_ticker_profile_fields(fingerprint))
    data.update(_serialize_sector_context_fields(fingerprint))
    data.update(_serialize_company_quality_fields(fingerprint))
    data.update(_serialize_alpha_trigger_fields(fingerprint))
    data.update(_serialize_volatility_fields(fingerprint))
    return data


def signal_observation_fingerprint_from_dict(
    cls, data: dict[str, Any]
) -> Any:
    """Reconstruct a SignalObservationFingerprint from a flat dictionary."""
    kwargs = {}
    kwargs.update(_parse_setup_fields(data))
    kwargs.update(_parse_strategy_fields(data))
    kwargs.update(_parse_flow_fields(data))
    kwargs.update(_parse_regime_fields(data))
    kwargs.update(_parse_institutional_accumulation_fields(data))
    kwargs.update(_parse_ticker_profile_fields(data))
    kwargs.update(_parse_sector_context_fields(data))
    kwargs.update(_parse_company_quality_fields(data))
    kwargs.update(_parse_alpha_trigger_fields(data))
    kwargs.update(_parse_volatility_fields(data))
    return cls(**kwargs)
