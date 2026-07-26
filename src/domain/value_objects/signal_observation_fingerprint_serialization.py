"""Serialization and parsing logic for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturn
from src.domain.value_objects.signal_assessment import SignalAssessmentIdentity

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


_CANONICAL_LABEL_FORBIDDEN_FINGERPRINT_KEYS = frozenset(
    {
        "coverage",
        "conviction",
        "phase_strength",
        "phase_coverage_score",
        "phase_conviction_score",
    }
)


def signal_observation_fingerprint_to_canonical_dict(
    fingerprint: "SignalObservationFingerprint",
) -> dict[str, Any]:
    data = signal_observation_fingerprint_to_dict(fingerprint)
    for key in _CANONICAL_LABEL_FORBIDDEN_FINGERPRINT_KEYS:
        data.pop(key, None)
    return data


def signal_observation_fingerprint_to_dict(
    fingerprint: "SignalObservationFingerprint",
) -> dict[str, Any]:
    """Serialize a SignalObservationFingerprint to a flat dictionary."""
    data = {
        "signal_assessment_identity": (
            fingerprint.signal_assessment_identity.to_dict()
            if fingerprint.signal_assessment_identity is not None
            else None
        )
    }
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
    # Benchmark excess returns serialization
    data.update({
        "benchmark_excess_return_5_session": (
            fingerprint.benchmark_excess_return_5_session.to_dict()
            if fingerprint.benchmark_excess_return_5_session is not None
            else None
        ),
        "benchmark_excess_return_20_session": (
            fingerprint.benchmark_excess_return_20_session.to_dict()
            if fingerprint.benchmark_excess_return_20_session is not None
            else None
        ),
        "benchmark_excess_return_authority_status": fingerprint.benchmark_excess_return_authority_status,
    })
    return data


def signal_observation_fingerprint_from_dict(
    cls, data: dict[str, Any]
) -> Any:
    """Reconstruct a SignalObservationFingerprint from a flat dictionary."""
    identity_data = data.get("signal_assessment_identity")
    kwargs = {
        "signal_assessment_identity": (
            SignalAssessmentIdentity.from_dict(identity_data)
            if identity_data is not None
            else None
        )
    }
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
    # Benchmark excess returns parsing
    r5_data = data.get("benchmark_excess_return_5_session")
    r20_data = data.get("benchmark_excess_return_20_session")
    kwargs.update({
        "benchmark_excess_return_5_session": (
            BenchmarkExcessReturn.from_dict(r5_data)
            if r5_data is not None
            else None
        ),
        "benchmark_excess_return_20_session": (
            BenchmarkExcessReturn.from_dict(r20_data)
            if r20_data is not None
            else None
        ),
        "benchmark_excess_return_authority_status": data.get("benchmark_excess_return_authority_status"),
    })
    return cls(**kwargs)
