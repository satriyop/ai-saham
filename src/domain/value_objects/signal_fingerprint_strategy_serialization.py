"""Strategy-section serialization for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_label_parsing import _optional_float

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


def _serialize_strategy_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "strategy_name": fp.strategy_name,
        "strategy_rule_name": fp.strategy_rule_name,
        "strategy_rule_outcome": fp.strategy_rule_outcome,
        "strategy_evidence_route": fp.strategy_evidence_route,
        "strategy_evidence_outcome": fp.strategy_evidence_outcome,
        "strategy_coverage_score": fp.strategy_coverage_score,
        "strategy_conviction_score": fp.strategy_conviction_score,
        "strategy_freshness_score": fp.strategy_freshness_score,
        "strategy_rationale": list(fp.strategy_rationale),
    }


def _parse_strategy_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_name": data.get("strategy_name"),
        "strategy_rule_name": data.get("strategy_rule_name"),
        "strategy_rule_outcome": data.get("strategy_rule_outcome"),
        "strategy_evidence_route": data.get("strategy_evidence_route"),
        "strategy_evidence_outcome": data.get("strategy_evidence_outcome"),
        "strategy_coverage_score": _optional_float(data.get("strategy_coverage_score")),
        "strategy_conviction_score": _optional_float(data.get("strategy_conviction_score")),
        "strategy_freshness_score": _optional_float(data.get("strategy_freshness_score")),
        "strategy_rationale": tuple(
            str(v) for v in data.get("strategy_rationale") or ()
        ),
    }
