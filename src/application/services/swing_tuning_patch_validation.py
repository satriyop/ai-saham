"""Validation policy and validator for exported swing tuning patch artifacts.

Layer: Application
"""

from __future__ import annotations

import json
from datetime import date
from fnmatch import fnmatch
from pathlib import Path

from src.application.services.swing_tuning_config_paths import (
    DocumentLoader,
    parse_tuning_config_path,
    resolve_tuning_config_value,
)
from src.application.services.swing_tuning_patch_readiness import (
    _validate_sample_readiness,
)
from src.application.services.swing_tuning_patch_reports import (
    SwingTuningPatchItemValidation,
    SwingTuningPatchValidationReport,
    _invalid_report,
)

# Phase 8: per-parameter walk-forward calibration guardrails.
# (document_path_pattern, min_value, max_value, step, max_shift_per_cycle)
# document_path_pattern: the part after the colon in the target_path.
# step: None means no quantization check.
# max_shift_per_cycle: maximum absolute change allowed in one tuning cycle.
_PARAMETER_BOUNDS: tuple[tuple[str, float, float, float | None, float], ...] = (
    # --- signal_engine paths ---
    ("signal_engine.evidence_groups.setup_quality.weight", 0.05, 1.0, 0.05, 0.10),
    ("signal_engine.evidence_groups.flow_confirmation.weight", 0.05, 1.0, 0.05, 0.10),
    ("signal_engine.flags.valuation_stretched.score_penalty", 0, 25, 1, 5),
    ("signal_engine.flags.analyst_bearish.score_penalty", 0, 25, 1, 5),
    ("signal_engine.flags.insider_selling.score_penalty", 0, 25, 1, 5),
    ("signal_engine.classification.strong_min_score", 50, 90, 1, 5),
    ("signal_engine.classification.moderate_min_score", 25, 70, 1, 5),
    ("signal_engine.decision_policy.regime_policy.*.enter_threshold", 50.0, 90.0, 1.0, 5.0),
    ("signal_engine.decision_policy.regime_policy.*.watch_threshold", 25.0, 80.0, 1.0, 5.0),
    (
        "signal_engine.decision_policy.regime_policy.*.min_signal_authority_coverage",
        0.0,
        1.0,
        0.05,
        0.10,
    ),
    ("signal_engine.decision_policy.regime_policy.*.regime_size_multiplier", 0.0, 1.0, 0.05, 0.10),
    ("signal_engine.alpha_trigger.low_weight_cap", 0.0, 0.25, 0.05, 0.05),
    ("signal_engine.alpha_trigger.group_weights.*", 0.0, 1.0, 0.05, 0.10),
    ("signal_engine.alpha_trigger.horizon_alpha_weights.*", 0.0, 1.0, 0.05, 0.10),
    ("signal_engine.alpha_trigger.route_fractions.*.*.alpha_fraction", 0.0, 1.0, 0.05, 0.10),
    # regime_conditioning.* removed from tunable paths: transitional legacy layer (TD-1).
    # Patches targeting regime_conditioning.* will now be rejected as out-of-bounds.
    # --- market_context_engine paths ---
    ("market_context_engine.regime_thresholds.risk_on_min_score", 0.45, 0.85, 0.05, 0.10),
    ("market_context_engine.regime_thresholds.risk_off_max_score", 0.15, 0.55, 0.05, 0.10),
    ("market_context_engine.regime_thresholds.volatile_vix_override", 20.0, 50.0, 1.0, 5.0),
    ("market_context_engine.regime_effects.RISK_OFF.signal_multiplier", 0.20, 1.0, 0.05, 0.10),
    ("market_context_engine.regime_effects.VOLATILE.signal_multiplier", 0.20, 1.0, 0.05, 0.10),
    # --- swing_targets paths ---
    ("setup_targets.*.take_profit_pct", 1.0, 15.0, 0.5, 2.0),
    ("setup_targets.*.stop_loss_pct", 1.0, 10.0, 0.5, 2.0),
    # --- swing_backtest reporting bucket paths ---
    ("swing_backtest.attribution.score_buckets.high_min_score", 50.0, 90.0, 1.0, 5.0),
    ("swing_backtest.attribution.score_buckets.mid_min_score", 25.0, 70.0, 1.0, 5.0),
    # --- swing_setups paths (fnmatch wildcard on setup name) ---
    ("setups.*.gates.max_bb_width_pctile", 0.05, 0.50, 0.05, 0.10),
    ("setups.*.gates.max_rsi", 25, 80, 1, 5),
    ("setups.*.gates.min_rsi", 15, 60, 1, 5),
    ("setups.*.gates.min_flow_ratio_pct", 0.5, 25.0, 0.5, 2.0),
    # Rescaled 0-120 -> 0-100 (ADR-039): 30-90 -> 25-75.
    ("setups.*.gates.min_accum_score", 25.0, 75.0, 1.0, 4.0),
    ("setups.*.gates.min_vwap_discount_pct", -5.0, 15.0, 0.5, 1.5),
    ("setups.*.gates.min_smart_flow_idr", 0.0, 1e12, 1e9, 5e10),
    ("setups.*.gates.min_smart_share_pct", 0.0, 100.0, 1.0, 10.0),
    ("setups.*.gates.max_noise_share_pct", 0.0, 100.0, 1.0, 10.0),
    ("setups.*.partial_max_failed_gates", 0, 5, 1, 1),
    # --- setup phase / RS policy paths ---
    # Rescaled 0-120 -> 0-100 (ADR-039): 30-90 -> 25-75. Field is currently
    # unused by SetupPhaseDetector (see config/swing_setups.yaml comment);
    # bounds kept in sync anyway to avoid a stale-scale trap if ever wired.
    ("setup_phase.thresholds.accumulation_min_flow_score", 25.0, 75.0, 1.0, 4.0),
    ("setup_phase.thresholds.accumulation_min_flow_ratio_pct", 0.5, 25.0, 0.5, 2.0),
    ("setup_phase.thresholds.compression_max_bb_width_pctile", 0.05, 0.50, 0.05, 0.10),
    ("setup_phase.thresholds.breakout_min_close_above_prev_high_pct", -2.0, 5.0, 0.5, 1.0),
    ("setup_phase.thresholds.breakout_reclaim_vwap_min_pct", -3.0, 5.0, 0.5, 1.0),
    ("setup_phase.thresholds.exhaustion_rsi_min", 60.0, 90.0, 1.0, 5.0),
    ("setup_phase.thresholds.exhaustion_min_price_extension_pct", 3.0, 20.0, 0.5, 3.0),
    ("setup_phase.thresholds.distribution_min_bandar_score", -9.0, 0.0, 1.0, 2.0),
    ("setup_phase.thresholds.failed_max_drawdown_from_recent_high_pct", -20.0, -2.0, 0.5, 2.0),
    ("setup_phase.thresholds.failed_breakdown_below_support_pct", -10.0, -0.5, 0.5, 2.0),
    # --- setup phase volume trigger paths (Point 3, explicit dry-up/expansion) ---
    ("setup_phase.volume_trigger.dry_up_max_ratio", 0.20, 0.80, 0.05, 0.10),
    ("setup_phase.volume_trigger.expansion_min_ratio", 1.10, 3.0, 0.1, 0.3),
    # --- risk_engine gate paths ---
    ("risk_engine.gates.free_float.min_free_float_pct", 10.0, 25.0, 0.5, 2.0),
    ("risk_engine.gates.fundamental.piotroski_min", 1, 7, 1, 1),
    ("risk_engine.gates.liquidity.market_cap_floor_idr", 1e11, 5e12, 1e11, 5e11),
    ("risk_engine.gates.liquidity.median_tx_floor_idr", 1e9, 5e10, 1e9, 5e9),
)

_NON_TUNABLE_DOCUMENT_PATHS: tuple[tuple[str, str], ...] = (
    ("signal_engine", "container_path_not_patchable"),
    ("signal_engine.classification", "container_path_not_patchable"),
    ("signal_engine.evidence_groups", "container_path_not_patchable"),
    ("signal_engine.flags", "container_path_not_patchable"),
    ("signal_engine.factors", "removed_legacy_baseline"),
    ("signal_engine.factors.*", "removed_legacy_baseline"),
    ("signal_engine.scoring.seasonality", "removed_non_operational_diagnostic_config"),
    ("signal_engine.scoring.seasonality.*", "removed_non_operational_diagnostic_config"),
    ("signal_engine.scoring.analyst", "removed_non_operational_diagnostic_config"),
    ("signal_engine.scoring.analyst.*", "removed_non_operational_diagnostic_config"),
    ("signal_engine.scoring.forward_pe", "removed_non_operational_diagnostic_config"),
    ("signal_engine.scoring.forward_pe.*", "removed_non_operational_diagnostic_config"),
    ("signal_engine.scoring.bandar", "legacy_scoring_container_not_patchable"),
    ("signal_engine.decision_policy", "container_path_not_patchable"),
    ("signal_engine.decision_policy.regime_policy", "container_path_not_patchable"),
    ("signal_engine.decision_policy.regime_policy.*", "container_path_not_patchable"),
    (
        "signal_engine.decision_policy.regime_policy.*.enter_allowed",
        "boolean_regime_policy_not_numeric_tunable",
    ),
    (
        "signal_engine.decision_policy.regime_policy.*.max_decision",
        "categorical_regime_policy_not_numeric_tunable",
    ),
    (
        "signal_engine.decision_policy.setup_regime_policy",
        "categorical_setup_regime_policy_not_numeric_tunable",
    ),
    (
        "signal_engine.decision_policy.setup_regime_policy.*",
        "categorical_setup_regime_policy_not_numeric_tunable",
    ),
    (
        "signal_engine.decision_policy.setup_regime_policy.*.*",
        "categorical_setup_regime_policy_not_numeric_tunable",
    ),
    ("risk_engine", "container_path_not_patchable"),
    ("risk_engine.gates", "container_path_not_patchable"),
    ("market_context_engine", "container_path_not_patchable"),
    ("setup_targets", "container_path_not_patchable"),
    ("swing_backtest.attribution.score_buckets", "container_path_not_patchable"),
    ("setups.*.gates.required_trend", "categorical_setup_gate_not_numeric_tunable"),
    ("setups.*.gates.reject_smart_net_selling", "boolean_setup_gate_not_numeric_tunable"),
    (
        "setup_phase.volume_trigger.require_trusted_volume",
        "boolean_volume_policy_not_numeric_tunable",
    ),
    (
        "setup_phase.volume_trigger.trusted_benchmark_volume_sources",
        "list_volume_policy_not_numeric_tunable",
    ),
    ("setup_phase.volume_trigger.dry_up_lookback_sessions", "window_size_not_numeric_tunable"),
    ("setup_phase.volume_trigger.dry_up_reference_sessions", "window_size_not_numeric_tunable"),
    (
        "setup_phase.volume_trigger.expansion_requires_positive_close",
        "boolean_volume_policy_not_numeric_tunable",
    ),
    # Point 3: superseded by volume_trigger.dry_up_max_ratio / expansion_min_ratio.
    # No longer read by _constructive_phase() — patching it would have zero
    # behavioral effect, so it must not be patch-eligible.
    ("setup_phase.thresholds.breakout_min_volume_ratio", "superseded_by_volume_trigger_policy"),
    # Evidence authority (DIAGNOSTIC/LOW_WEIGHT/PRODUCTION) and its promotion
    # record are a manual-review guardrail (see bootstrap._validate_promotion_record),
    # not a walk-forward tuning target. A tuning patch must never silently
    # promote diagnostic evidence into scoring authority.
    (
        "signal_engine.alpha_trigger.evidence_registrations.*.status",
        "evidence_authority_promotion_requires_manual_review",
    ),
    (
        "signal_engine.alpha_trigger.evidence_registrations.*.promotion",
        "evidence_authority_promotion_requires_manual_review",
    ),
    (
        "signal_engine.alpha_trigger.evidence_registrations.*.promotion.*",
        "evidence_authority_promotion_requires_manual_review",
    ),
)


def _bounds_for_document_path(
    document_path: str,
) -> tuple[float, float, float | None, float] | None:
    """Return (min, max, step, max_shift) if document_path matches a bounds policy.

    Patterns containing '*' are matched with fnmatch; others require exact equality.
    """
    for pattern, lo, hi, step, max_shift in _PARAMETER_BOUNDS:
        match = fnmatch(document_path, pattern) if "*" in pattern else document_path == pattern
        if match:
            return (lo, hi, step, max_shift)
    return None


def _non_tunable_reason_for_document_path(document_path: str) -> str | None:
    for pattern, reason in _NON_TUNABLE_DOCUMENT_PATHS:
        match = fnmatch(document_path, pattern) if "*" in pattern else document_path == pattern
        if match:
            return reason
    return None


def _is_quantized(value: float, step: float) -> bool:
    """True when value is a multiple of step within floating-point tolerance."""
    if step <= 0:
        return True
    remainder = abs(value % step)
    return remainder < 1e-9 or abs(remainder - step) < 1e-9


class SwingTuningPatchValidator:
    def __init__(self, document_loader: DocumentLoader) -> None:
        self._document_loader = document_loader

    def validate(self, patch_path: Path) -> SwingTuningPatchValidationReport:
        try:
            payload = json.loads(patch_path.read_text())
        except FileNotFoundError:
            return _invalid_report(str(patch_path), "patch_file_not_found")
        except json.JSONDecodeError:
            return _invalid_report(str(patch_path), "patch_json_invalid")

        issues: list[str] = []
        artifact_type = _str(payload.get("artifact_type"))
        if artifact_type != "swing_tuning_patch_review":
            issues.append("artifact_type_must_be_swing_tuning_patch_review")

        apply_block = payload.get("apply")
        if not isinstance(apply_block, dict) or apply_block.get("supported") is not False:
            issues.append("apply_supported_must_be_false")

        source_review = payload.get("source_review")
        issues.extend(_validate_walk_forward_source_review(source_review))
        issues.extend(_validate_sample_readiness(source_review))

        patch_items = payload.get("patch_items")
        if not isinstance(patch_items, list):
            issues.append("patch_items_must_be_list")
            patch_items = []

        seen_paths: set[str] = set()
        item_results = tuple(
            self._validate_item(item, seen_paths=seen_paths) for item in patch_items
        )
        valid = not issues and all(item.valid for item in item_results)
        return SwingTuningPatchValidationReport(
            patch_path=str(patch_path),
            valid=valid,
            artifact_type=artifact_type,
            item_count=len(patch_items),
            valid_item_count=sum(1 for item in item_results if item.valid),
            issues=tuple(issues),
            item_results=item_results,
        )

    def _validate_item(
        self,
        item: object,
        seen_paths: set[str],
    ) -> SwingTuningPatchItemValidation:
        item_issues: list[str] = []
        item_dict = item if isinstance(item, dict) else {}
        if not item_dict:
            item_issues.append("patch_item_must_be_object")

        target_path = _str(item_dict.get("target_path"))
        proposed_value = item_dict.get("proposed_value")
        current_value = item_dict.get("current_value")
        resolved_current_value: object | None = None
        document_path: str | None = None

        if not target_path:
            item_issues.append("target_path_required")
        elif target_path in seen_paths:
            item_issues.append("duplicate_target_path")
        elif target_path is not None:
            seen_paths.add(target_path)

        if proposed_value is None:
            item_issues.append("proposed_value_required")

        if target_path:
            if "regime_conditioning" in target_path:
                item_issues.append("target_path_not_tunable:regime_conditioning_is_legacy_layer")
            else:
                try:
                    parsed = parse_tuning_config_path(target_path)
                except ValueError:
                    item_issues.append("target_path_invalid")
                else:
                    document_path = parsed.document_path
                    non_tunable_reason = _non_tunable_reason_for_document_path(document_path)
                    if non_tunable_reason is not None:
                        item_issues.append(f"target_path_not_tunable:{non_tunable_reason}")
                    resolution = resolve_tuning_config_value(
                        parsed,
                        document_loader=self._document_loader,
                    )
                    if not resolution.resolved:
                        item_issues.append(f"target_path_unresolved:{resolution.unresolved_reason}")
                    else:
                        resolved_current_value = resolution.current_value
                        if current_value != resolution.current_value:
                            item_issues.append("current_value_mismatch")
                        if not _type_compatible(
                            resolution.current_value,
                            proposed_value,
                        ):
                            item_issues.append("proposed_value_type_mismatch")
                        elif (
                            non_tunable_reason is None
                            and _bounds_for_document_path(document_path) is None
                        ):
                            item_issues.append("target_path_unbounded")

        # Phase 8: parameter bounds — range, quantization, per-cycle shift cap.
        if (
            resolved_current_value is not None
            and proposed_value is not None
            and document_path is not None
            and not item_issues
        ):
            bounds = _bounds_for_document_path(document_path)
            if bounds is not None:
                lo, hi, step, max_shift = bounds
                try:
                    pv: float | None = float(proposed_value)
                    cv: float | None = float(resolved_current_value)
                except (TypeError, ValueError):
                    pv = cv = None
                if pv is not None:
                    if not (lo <= pv <= hi):
                        item_issues.append(f"proposed_value_out_of_range:[{lo},{hi}]")
                    if step is not None and not _is_quantized(pv, step):
                        item_issues.append(f"proposed_value_not_quantized:step={step}")
                    if cv is not None and abs(pv - cv) > max_shift + 1e-9:
                        item_issues.append(f"proposed_value_exceeds_shift_cap:{max_shift}")

        return SwingTuningPatchItemValidation(
            target_path=target_path,
            valid=not item_issues,
            current_value=resolved_current_value,
            proposed_value=proposed_value,
            issues=tuple(item_issues),
        )


def _validate_walk_forward_source_review(source_review: object) -> tuple[str, ...]:
    """Return a tuple of issue strings for walk-forward provenance violations.

    All issues are prefixed with 'walk_forward_not_enforced:' so callers can
    detect the category with a single substring check.
    """
    prefix = "walk_forward_not_enforced:"
    issues: list[str] = []
    if not isinstance(source_review, dict):
        return (f"{prefix} source_review must be a dict",)
    if source_review.get("walk_forward_enforced") is not True:
        issues.append(f"{prefix} walk_forward_enforced must be exactly true (boolean)")
    try:
        ir = float(source_review.get("is_ratio"))  # type: ignore[arg-type]
        if not (0.0 < ir < 1.0):
            issues.append(f"{prefix} is_ratio must be in (0.0, 1.0), got {ir}")
    except (TypeError, ValueError):
        issues.append(f"{prefix} is_ratio must be a number in (0.0, 1.0)")
    is_end_date_raw = source_review.get("is_end_date")
    oos_start_date_raw = source_review.get("oos_start_date")
    full_end_date_raw = source_review.get("full_end_date")
    if not is_end_date_raw:
        issues.append(f"{prefix} is_end_date is required")
    if not oos_start_date_raw:
        issues.append(f"{prefix} oos_start_date is required")
    if not full_end_date_raw:
        issues.append(f"{prefix} full_end_date is required")
    if is_end_date_raw and oos_start_date_raw and full_end_date_raw:
        try:
            is_end = date.fromisoformat(str(is_end_date_raw))
            oos_start = date.fromisoformat(str(oos_start_date_raw))
            full_end = date.fromisoformat(str(full_end_date_raw))
            if not (is_end < oos_start <= full_end):
                issues.append(
                    f"{prefix} date ordering violated: "
                    f"is_end_date={is_end} oos_start_date={oos_start} "
                    f"full_end_date={full_end}; "
                    "require is_end_date < oos_start_date <= full_end_date"
                )
        except ValueError as exc:
            issues.append(f"{prefix} date parse error: {exc}")
    oos = source_review.get("oos_backtest_summary")
    if not isinstance(oos, dict):
        issues.append(f"{prefix} oos_backtest_summary must be a dict")
    else:
        try:
            int(oos.get("trade_count"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            issues.append(f"{prefix} oos_backtest_summary.trade_count must be an integer")
        if "total_return_pct" not in oos:
            issues.append(
                f"{prefix} oos_backtest_summary.total_return_pct is required (may be null)"
            )
        if "win_rate_pct" not in oos:
            issues.append(f"{prefix} oos_backtest_summary.win_rate_pct is required (may be null)")
    return tuple(issues)


def _str(value: object) -> str | None:
    return str(value) if value is not None else None


def _type_compatible(current_value: object, proposed_value: object) -> bool:
    if proposed_value is None:
        return False
    if isinstance(current_value, bool):
        return isinstance(proposed_value, bool)
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        return isinstance(proposed_value, int) and not isinstance(proposed_value, bool)
    if isinstance(current_value, float):
        return isinstance(proposed_value, int | float) and not isinstance(proposed_value, bool)
    if isinstance(current_value, str):
        return isinstance(proposed_value, str)
    return type(proposed_value) is type(current_value)
