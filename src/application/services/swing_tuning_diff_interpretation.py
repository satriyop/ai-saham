"""Interpretation logic and prioritization for swing tuning config diffs.

Layer: Application
"""

from __future__ import annotations


def tuning_config_diff_item_interpretation(
    status: str,
    value_selection_policy: str,
) -> str:
    if status == "PROPOSED_VALUE_SELECTED":
        return "proposed guarded value"
    return {
        "NON_NUMERIC_CURRENT_VALUE": (
            "read-only current value; non-numeric config"
        ),
        "INSUFFICIENT_EVIDENCE": (
            "read-only current value; evidence below high"
        ),
        "NO_DETERMINISTIC_DIRECTION": (
            "read-only current value; no deterministic direction"
        ),
        "NO_UNAMBIGUOUS_DIRECTION": (
            "read-only current value; unsupported direction"
        ),
    }.get(value_selection_policy, "read-only current value")


def tuning_config_diff_rejection_interpretation(
    value_selection_policy: str,
) -> str:
    return {
        "INSUFFICIENT_EVIDENCE": "not resolved; readiness blocked",
        "CONFIG_FILE_NOT_FOUND": "not resolved; config file missing",
        "DOCUMENT_PATH_NOT_FOUND": "not resolved; YAML path missing",
        "WILDCARD_UNRESOLVED": "not resolved; wildcard target unresolved",
        "CONFIG_VALUE_NOT_RESOLVED": (
            "not resolved; config value unavailable"
        ),
    }.get(value_selection_policy, "not resolved")


def tuning_diff_item_priority(item) -> int:
    if item.proposed_value is not None:
        return 100
    return {
        "DETERMINISTIC_VALUE_SELECTED": 100,
        "NO_DETERMINISTIC_DIRECTION": 80,
        "INSUFFICIENT_EVIDENCE": 70,
        "NO_UNAMBIGUOUS_DIRECTION": 60,
        "NON_NUMERIC_CURRENT_VALUE": 50,
    }.get(item.value_selection_policy, 10)
