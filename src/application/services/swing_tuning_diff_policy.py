"""Deterministic policy helpers for swing tuning config diff drafts.

Intent:
    Select bounded dry-run values, classify targets, and build review metadata.
    This module never mutates YAML and never generates applyable diffs.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.application.services.swing_tuning_config_paths import (
    TuningConfigPath,
    TuningConfigValueResolution,
)


@dataclass(frozen=True)
class TuningValueSuggestion:
    """Deterministic value-selection result for a config diff item."""

    proposed_value: object | None
    rationale: str
    confidence: str
    status: str
    value_selection_policy: str


@dataclass(frozen=True)
class TuningTargetClassification:
    """Derived semantic classification for one YAML tuning target."""

    target_family: str
    target_kind: str
    target_parameter: str

    @classmethod
    def from_path(
        cls,
        target_path: TuningConfigPath | None,
    ) -> TuningTargetClassification:
        if target_path is None:
            return cls(
                target_family="unknown",
                target_kind="unknown",
                target_parameter="unknown",
            )
        return cls(
            target_family=_classify_tuning_target_family(target_path),
            target_kind=_classify_tuning_target_kind(target_path),
            target_parameter=_tuning_target_parameter(target_path),
        )

    def to_dict(self) -> dict:
        return {
            "target_family": self.target_family,
            "target_kind": self.target_kind,
            "target_parameter": self.target_parameter,
        }


def build_tuning_config_diff_summary(
    diff_items: tuple[object, ...],
    rejected_items: tuple[object, ...],
) -> dict[str, object]:
    value_policy_counts = _count_strings(
        item.value_selection_policy for item in diff_items
    )
    evidence_dimension_counts = _count_strings(
        dimension
        for item in diff_items
        for dimension in (
            item.evidence_dimensions or (item.evidence_dimension,)
        )
    )
    return {
        "resolved_count": len(diff_items),
        "proposed_count": sum(
            1 for item in diff_items if item.proposed_value is not None
        ),
        "current_only_count": sum(
            1 for item in diff_items if item.proposed_value is None
        ),
        "rejected_count": len(rejected_items),
        "value_policy_counts": value_policy_counts,
        "evidence_dimension_counts": evidence_dimension_counts,
    }


def build_tuning_config_diff_review_checklist(
    diff_items: tuple[object, ...],
    rejected_items: tuple[object, ...],
) -> tuple[str, ...]:
    checklist = [
        "Confirm sample size is sufficient for the target evidence.",
        "Confirm return spread is stable across the evidence buckets.",
        "Confirm proposed value direction matches the setup intent.",
    ]
    if any(item.proposed_value is not None for item in diff_items):
        checklist.append(
            "Review every proposed value before editing YAML manually."
        )
    if any(item.proposed_value is None for item in diff_items):
        checklist.append(
            "Inspect current-only rows before treating them as tunable."
        )
    if rejected_items:
        checklist.append(
            "Resolve rejected rows before expecting a complete tuning diff."
        )
    checklist.append(
        "Do not apply automatically; edit YAML manually only after review."
    )
    return tuple(checklist)


def value_selection_policy_for_rejection(unresolved_reason: str | None) -> str:
    return {
        "wildcard_path_not_resolved": "WILDCARD_UNRESOLVED",
        "config_file_not_found": "CONFIG_FILE_NOT_FOUND",
        "document_path_not_found": "DOCUMENT_PATH_NOT_FOUND",
    }.get(unresolved_reason or "", "CONFIG_VALUE_NOT_RESOLVED")


def suggest_tuning_value(
    candidate,
    resolution: TuningConfigValueResolution,
) -> TuningValueSuggestion:
    """Select a bounded deterministic value only for narrow safe cases."""
    current_value = resolution.current_value
    if not _is_tunable_number(current_value):
        return TuningValueSuggestion(
            proposed_value=None,
            rationale=(
                "Current value resolved, but only numeric non-boolean config "
                "values are eligible for deterministic value-selection."
            ),
            confidence="READ_ONLY_CURRENT_VALUE",
            status="CURRENT_VALUE_ONLY",
            value_selection_policy="NON_NUMERIC_CURRENT_VALUE",
        )

    if candidate.evidence_strength != "HIGH":
        return TuningValueSuggestion(
            proposed_value=None,
            rationale=(
                "Current value resolved, but evidence strength is not HIGH."
            ),
            confidence="READ_ONLY_CURRENT_VALUE",
            status="CURRENT_VALUE_ONLY",
            value_selection_policy="INSUFFICIENT_EVIDENCE",
        )

    adjustment_direction = _deterministic_adjustment_direction(
        candidate,
        resolution.target_path,
    )
    if adjustment_direction is None:
        return TuningValueSuggestion(
            proposed_value=None,
            rationale=(
                "Current numeric value resolved, but attribution buckets do not "
                "support a deterministic value direction for this path."
            ),
            confidence="READ_ONLY_CURRENT_VALUE",
            status="CURRENT_VALUE_ONLY",
            value_selection_policy="NO_DETERMINISTIC_DIRECTION",
        )

    if adjustment_direction == 0:
        return TuningValueSuggestion(
            proposed_value=None,
            rationale=(
                "Current numeric value resolved, but the path does not expose "
                "an eligible threshold/weight/exit direction."
            ),
            confidence="READ_ONLY_CURRENT_VALUE",
            status="CURRENT_VALUE_ONLY",
            value_selection_policy="NO_UNAMBIGUOUS_DIRECTION",
        )

    proposed_value = _bounded_one_step_adjustment(
        current_value,
        adjustment_direction,
    )
    return TuningValueSuggestion(
        proposed_value=proposed_value,
        rationale=(
            "HIGH evidence and an eligible numeric path allow a bounded "
            "one-step deterministic dry-run proposal for human review."
        ),
        confidence="DETERMINISTIC_GUARDED",
        status="PROPOSED_VALUE_SELECTED",
        value_selection_policy="DETERMINISTIC_VALUE_SELECTED",
    )


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


def _classify_tuning_target_family(target_path: TuningConfigPath) -> str:
    file_name = target_path.file_path.rsplit("/", maxsplit=1)[-1]
    stem = file_name.rsplit(".", maxsplit=1)[0]
    return {
        "signal_engine": "signal_engine",
        "swing_risk_policy": "risk_policy",
        "swing_setups": "swing_setup",
        "market_context_engine": "market_context",
    }.get(stem, stem or "unknown")


def _classify_tuning_target_kind(target_path: TuningConfigPath) -> str:
    document_path = target_path.document_path
    leaf = _tuning_target_parameter(target_path)
    segments = document_path.split(".")
    if "classification" in segments:
        return "classification"
    if "gates" in segments:
        return "gate"
    if "weights" in segments or leaf.endswith("_weight"):
        return "weight"
    if _is_exit_rule_parameter(leaf, segments):
        return "exit_rule"
    if _is_threshold_parameter(leaf):
        return "threshold"
    return "unknown"


def _tuning_target_parameter(target_path: TuningConfigPath) -> str:
    return target_path.document_path.rsplit(".", maxsplit=1)[-1] or "unknown"


def _is_threshold_parameter(parameter: str) -> bool:
    return (
        parameter.startswith(("min_", "max_"))
        or parameter.endswith(("_threshold", "_min", "_max", "_score"))
        or "max_failed_gates" in parameter
    )


def _is_exit_rule_parameter(
    parameter: str,
    segments: list[str],
) -> bool:
    exit_terms = (
        "exit",
        "take_profit",
        "stop_loss",
        "trailing_stop",
        "max_hold",
    )
    return any(term in parameter for term in exit_terms) or any(
        term in segment for segment in segments for term in exit_terms
    )


def _is_tunable_number(value: object | None) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _deterministic_adjustment_direction(
    candidate,
    target_path: TuningConfigPath,
) -> int | None:
    if _evidence_supports_tightening(candidate):
        return _tighten_adjustment_direction(target_path)
    if _evidence_supports_loosening(candidate):
        return _loosen_adjustment_direction(target_path)
    return None


def _tighten_adjustment_direction(target_path: TuningConfigPath) -> int:
    threshold_direction = _numeric_adjustment_direction(target_path)
    if threshold_direction != 0:
        return threshold_direction

    path = target_path.document_path.lower()
    if ".take_profit_pct" in path:
        return 1
    if ".stop_loss_pct" in path:
        return -1
    if path.endswith(".signal_multiplier"):
        return -1
    if path.endswith(".partial_max_failed_gates"):
        return -1
    return 0


def _loosen_adjustment_direction(target_path: TuningConfigPath) -> int:
    threshold_direction = _numeric_adjustment_direction(target_path)
    if threshold_direction != 0:
        return -threshold_direction

    path = target_path.document_path.lower()
    if ".take_profit_pct" in path:
        return -1
    if ".stop_loss_pct" in path:
        return 1
    if path.endswith(".signal_multiplier"):
        return 1
    if path.endswith(".partial_max_failed_gates"):
        return 1
    return 0


def _numeric_adjustment_direction(target_path: TuningConfigPath) -> int:
    leaf_name = target_path.document_path.rsplit(".", maxsplit=1)[-1].lower()
    if any(token in leaf_name for token in ("min", "floor", "required", "bullish")):
        return 1
    if any(token in leaf_name for token in ("max", "ceiling", "bearish")):
        return -1
    return 0


def _bounded_one_step_adjustment(value: object, direction: int) -> int | float:
    if isinstance(value, int) and not isinstance(value, bool):
        return value + direction
    numeric_value = float(value)
    return round(numeric_value + (0.5 * direction), 4)


def _evidence_supports_tightening(candidate) -> bool:
    bucket_avgs = _evidence_bucket_avgs(candidate)
    if candidate.dimension in {
        "signal_strength",
        "candidate_signal_strength",
    }:
        strong_avg = bucket_avgs.get("STRONG")
        if strong_avg is None:
            return False
        return any(
            avg > strong_avg
            for label, avg in bucket_avgs.items()
            if label in {"MODERATE", "WEAK"}
        )
    if candidate.dimension in {
        "signal_score_bucket",
        "candidate_signal_score_bucket",
    }:
        high_avg = next(
            (
                avg
                for label, avg in bucket_avgs.items()
                if label.startswith("HIGH")
            ),
            None,
        )
        if high_avg is None:
            return False
        return any(
            avg > high_avg
            for label, avg in bucket_avgs.items()
            if label.startswith(("LOW", "MID"))
        )
    if candidate.dimension in {"candidate_setup_match", "setup_match"}:
        match_avg = bucket_avgs.get("MATCH")
        no_match_avg = bucket_avgs.get("NO_MATCH")
        return (
            match_avg is not None
            and no_match_avg is not None
            and match_avg > no_match_avg
        )
    if candidate.dimension == "setup_gate":
        return _setup_gate_pass_avg_beats_fail_avg(bucket_avgs)
    return False


def _evidence_supports_loosening(candidate) -> bool:
    bucket_avgs = _evidence_bucket_avgs(candidate)
    if candidate.dimension in {"candidate_setup_match", "setup_match"}:
        match_avg = bucket_avgs.get("MATCH")
        no_match_avg = bucket_avgs.get("NO_MATCH")
        return (
            match_avg is not None
            and no_match_avg is not None
            and no_match_avg > match_avg
        )
    if candidate.dimension == "setup_gate":
        return _setup_gate_fail_avg_beats_pass_avg(bucket_avgs)
    if candidate.dimension == "candidate_risk_status":
        open_avg = bucket_avgs.get("OPEN")
        blocked_avg = bucket_avgs.get("BLOCKED")
        return (
            blocked_avg is not None
            and open_avg is not None
            and blocked_avg > open_avg
        )
    return False


def _evidence_bucket_avgs(candidate) -> dict[str, float]:
    return {
        label: avg
        for label, avg in (
            _parse_evidence_bucket_avg(bucket)
            for bucket in candidate.evidence_buckets
        )
        if label and avg is not None
    }


def _setup_gate_pass_avg_beats_fail_avg(bucket_avgs: dict[str, float]) -> bool:
    gate_names = {
        label.rsplit(":", maxsplit=1)[0]
        for label in bucket_avgs
        if label.endswith((":PASS", ":FAIL"))
    }
    return any(
        bucket_avgs.get(f"{gate_name}:PASS") is not None
        and bucket_avgs.get(f"{gate_name}:FAIL") is not None
        and bucket_avgs[f"{gate_name}:PASS"] > bucket_avgs[f"{gate_name}:FAIL"]
        for gate_name in gate_names
    )


def _setup_gate_fail_avg_beats_pass_avg(bucket_avgs: dict[str, float]) -> bool:
    gate_names = {
        label.rsplit(":", maxsplit=1)[0]
        for label in bucket_avgs
        if label.endswith((":PASS", ":FAIL"))
    }
    return any(
        bucket_avgs.get(f"{gate_name}:PASS") is not None
        and bucket_avgs.get(f"{gate_name}:FAIL") is not None
        and bucket_avgs[f"{gate_name}:FAIL"] > bucket_avgs[f"{gate_name}:PASS"]
        for gate_name in gate_names
    )


def _parse_evidence_bucket_avg(bucket: str) -> tuple[str, float | None]:
    parts = tuple(part.strip() for part in bucket.split("|"))
    label = parts[0] if parts else ""
    avg_part = next(
        (part for part in parts if part.startswith("avg=")),
        "",
    )
    if not avg_part:
        return label, None
    try:
        return label, float(
            avg_part.removeprefix("avg=").removesuffix("%").replace("+", "")
        )
    except ValueError:
        return label, None


def _count_strings(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
