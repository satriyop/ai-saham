"""
Evidence authority promotion validation.

Validates alpha/trigger evidence registration promotion records (DIAGNOSTIC ->
LOW_WEIGHT -> PRODUCTION) against the Phase I promotion gates. Pure validation;
no engine construction, no infrastructure wiring.
"""

from __future__ import annotations

from datetime import date

_BASELINE_EVIDENCE_AUTHORITY = {
    ("setup_quality", "PRODUCTION"),
    ("institutional_flow", "PRODUCTION"),
}

_PROMOTED_STATUSES = {"LOW_WEIGHT", "PRODUCTION"}

_PHASE_I_PROMOTION_GATES = {
    "min_is_labels": (60.0, "min"),
    "min_oos_labels": (30.0, "min"),
    "min_oos_profit_factor": (1.15, "min"),
    "min_oos_avg_return_pct": (0.0, "min"),
    "max_drawdown_regression_pct": (0.0, "max"),
}


def _resolve_evidence_promotion_record(
    *,
    name: str,
    status,
    raw,
    evidence_promotion_record_cls,
    evidence_status_cls,
):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(
            f"signal_engine.alpha_trigger.evidence_registrations.{name}.promotion must be a mapping"
        )

    promoted_to_raw = str(raw.get("promoted_to", "")).upper()
    try:
        promoted_to = evidence_status_cls(promoted_to_raw)
    except ValueError:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.promoted_to must be DIAGNOSTIC, LOW_WEIGHT, or PRODUCTION"
        )

    record = evidence_promotion_record_cls(
        target=_promotion_required_str(name, raw, "target"),
        evidence_name=_promotion_required_str(name, raw, "evidence_name"),
        promoted_to=promoted_to,
        promoted_by=_promotion_required_str(name, raw, "promoted_by"),
        promoted_date=_promotion_required_str(name, raw, "promoted_date"),
        attribution_ref=_promotion_required_str(name, raw, "attribution_ref"),
        requirements=_promotion_requirements(name, raw.get("requirements")),
    )
    _validate_promotion_record(name=name, status=status, promotion=record)
    return record


def _promotion_required_str(name: str, raw: dict, field: str) -> str:
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.{field} is required"
        )
    return str(value).strip()


def _promotion_requirements(name: str, raw_requirements) -> tuple[tuple[str, float], ...]:
    if not isinstance(raw_requirements, dict):
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.requirements must be a mapping"
        )
    requirements: list[tuple[str, float]] = []
    for key in _PHASE_I_PROMOTION_GATES:
        if key not in raw_requirements:
            raise ValueError(
                "signal_engine.alpha_trigger.evidence_registrations."
                f"{name}.promotion.requirements.{key} is required"
            )
        try:
            requirements.append((key, float(raw_requirements[key])))
        except (TypeError, ValueError):
            raise ValueError(
                "signal_engine.alpha_trigger.evidence_registrations."
                f"{name}.promotion.requirements.{key} must be numeric"
            )
    return tuple(requirements)


def _validate_evidence_authority_promotion(*, name: str, status, promotion) -> None:
    status_value = status.value if hasattr(status, "value") else str(status)
    if (name, status_value) in _BASELINE_EVIDENCE_AUTHORITY:
        return
    if status_value in _PROMOTED_STATUSES and promotion is None:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion is required when status is {status_value}"
        )


def _validate_promotion_record(*, name: str, status, promotion) -> None:
    status_value = status.value if hasattr(status, "value") else str(status)
    if promotion.evidence_name != name:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.evidence_name must match registration key"
        )
    promoted_to = (
        promotion.promoted_to.value
        if hasattr(promotion.promoted_to, "value")
        else str(promotion.promoted_to)
    )
    if promoted_to != status_value:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.promoted_to must equal status"
        )
    try:
        date.fromisoformat(promotion.promoted_date)
    except ValueError:
        raise ValueError(
            "signal_engine.alpha_trigger.evidence_registrations."
            f"{name}.promotion.promoted_date must be a valid ISO date"
        )
    requirements = promotion.requirements_dict
    for key, (canonical, direction) in _PHASE_I_PROMOTION_GATES.items():
        value = requirements[key]
        if direction == "min" and value < canonical:
            raise ValueError(
                "signal_engine.alpha_trigger.evidence_registrations."
                f"{name}.promotion.requirements.{key} must be >= {canonical:g}"
            )
        if direction == "max" and value > canonical:
            raise ValueError(
                "signal_engine.alpha_trigger.evidence_registrations."
                f"{name}.promotion.requirements.{key} must be <= {canonical:g}"
            )
