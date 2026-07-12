"""Deterministic value suggestion policies for swing tuning config diffs.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch

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

    document_path = resolution.target_path.document_path
    custom_step = _custom_step_for(document_path)
    if custom_step is not None:
        proposed_value = _snap_to_step(float(current_value), custom_step, adjustment_direction)
    elif _should_snap_to_weight_grid(document_path):
        # Use the 0.05 grid step directly so proposals stay within parameter bounds.
        # Adding the generic 0.5 float step to e.g. confidence=0.70 would produce
        # 1.20, which exceeds the 0.90 ceiling and fails validator immediately.
        proposed_value = _snap_to_weight_grid(
            float(current_value) + _WEIGHT_STEP * adjustment_direction
        )
    else:
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


_WEIGHT_STEP = 0.05

# Phase 8: document-path suffixes whose float proposals must land on a 0.05 grid.
_QUANTIZED_STEP_PATHS = (
    "evidence_groups.setup_quality.weight",
    "evidence_groups.flow_confirmation.weight",
    "classification.enter_min_confidence",
    "classification.watch_min_confidence",
    # regime_conditioning.* removed: transitional layer — not to be tuned (TD-1)
)


def _snap_to_weight_grid(value: float) -> float:
    """Snap value to the nearest 0.05 multiple."""
    return round(round(value / _WEIGHT_STEP) * _WEIGHT_STEP, 4)


def _should_snap_to_weight_grid(document_path: str) -> bool:
    """True when the document path targets a 0.05-quantized weight/confidence param."""
    return any(document_path.endswith(suffix) for suffix in _QUANTIZED_STEP_PATHS)


# Per-path step overrides for large-magnitude parameters (e.g. IDR floor values).
# Format: (document_path_pattern, step). Supports fnmatch wildcards.
# Keep in sync with _PARAMETER_BOUNDS in swing_tuning_patch_validator.py.
_CUSTOM_STEP_OVERRIDES: tuple[tuple[str, float], ...] = (
    ("risk_engine.gates.liquidity.market_cap_floor_idr", 1e11),
    ("risk_engine.gates.liquidity.median_tx_floor_idr", 1e9),
)


def _custom_step_for(document_path: str) -> float | None:
    for pattern, step in _CUSTOM_STEP_OVERRIDES:
        if fnmatch(document_path, pattern) if "*" in pattern else document_path == pattern:
            return step
    return None


def _snap_to_step(value: float, step: float, direction: int) -> int | float:
    """Snap value to step grid then move one step in direction."""
    snapped = round(value / step) * step
    result = snapped + step * direction
    return int(result) if result == int(result) else round(result, 4)


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
