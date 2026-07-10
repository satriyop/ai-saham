"""Validation and guarded application for exported swing tuning patch artifacts.

Intent:
    Validate review-only patch JSON, plan exact YAML changes, and apply them
    only when explicit confirmation and target-cleanliness checks pass.

Layer: Application
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable

import yaml

from src.application.services.swing_tuning_config_paths import (
    parse_tuning_config_path,
    resolve_tuning_config_value,
)

TargetDirtyChecker = Callable[[Path], bool]


# Phase I target-state readiness gates. Diagnostic-ready findings are
# report-only; patch validation requires the stricter patch-eligible floor from
# docs/signal_refactor.md.
_DIAGNOSTIC_MIN_OOS_TRADE_COUNT: int = 10
_PATCH_MIN_IS_TRADE_COUNT: int = 60
_PATCH_MIN_OOS_TRADE_COUNT: int = 30
_PATCH_MIN_OOS_PROFIT_FACTOR: float = 1.15
_PATCH_MIN_OOS_AVERAGE_RETURN_PCT: float = 0.0
_PATCH_MAX_OOS_DRAWDOWN_REGRESSION: float = 0.0
_MAX_SINGLE_REGIME_OOS_PROFIT_SHARE: float = 0.70
_MIN_POSITIVE_OOS_REGIME_COUNT: int = 2
_MIN_OOS_TRADES_PER_COUNTED_REGIME: int = 5

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
    ("signal_engine.classification.enter_min_confidence", 0.40, 0.90, 0.05, 0.10),
    ("signal_engine.classification.watch_min_confidence", 0.20, 0.60, 0.05, 0.10),
    ("signal_engine.decision_policy.regime_policy.*.enter_threshold", 50.0, 90.0, 1.0, 5.0),
    ("signal_engine.decision_policy.regime_policy.*.watch_threshold", 25.0, 80.0, 1.0, 5.0),
    ("signal_engine.decision_policy.regime_policy.*.min_coverage", 0.0, 1.0, 0.05, 0.10),
    ("signal_engine.decision_policy.regime_policy.*.min_conviction", 0.0, 1.0, 0.05, 0.10),
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
    ("setups.*.gates.min_foreign_flow_score", 25.0, 75.0, 1.0, 4.0),
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
    ("setup_phase.rs_policy_by_setup_family.*.lag_warning_below", -10.0, 5.0, 0.5, 1.5),
    ("setup_phase.rs_policy_by_setup_family.*.hard_exclude_below", -20.0, 0.0, 0.5, 2.0),
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
    ("signal_engine.factors", "archived_baseline_only"),
    ("signal_engine.factors.*", "archived_baseline_only"),
    ("signal_engine.scoring.seasonality", "diagnostic_company_quality_not_patch_eligible"),
    ("signal_engine.scoring.seasonality.*", "diagnostic_company_quality_not_patch_eligible"),
    ("signal_engine.scoring.analyst", "diagnostic_company_quality_not_patch_eligible"),
    ("signal_engine.scoring.analyst.*", "diagnostic_company_quality_not_patch_eligible"),
    ("signal_engine.scoring.forward_pe", "diagnostic_company_quality_not_patch_eligible"),
    ("signal_engine.scoring.forward_pe.*", "diagnostic_company_quality_not_patch_eligible"),
    ("signal_engine.scoring.bandar", "legacy_scoring_container_not_patchable"),
    ("signal_engine.decision_policy", "container_path_not_patchable"),
    ("signal_engine.decision_policy.regime_policy", "container_path_not_patchable"),
    ("signal_engine.decision_policy.regime_policy.*", "container_path_not_patchable"),
    ("signal_engine.decision_policy.regime_policy.*.enter_allowed", "boolean_regime_policy_not_numeric_tunable"),
    ("signal_engine.decision_policy.regime_policy.*.max_decision", "categorical_regime_policy_not_numeric_tunable"),
    ("signal_engine.decision_policy.setup_regime_policy", "categorical_setup_regime_policy_not_numeric_tunable"),
    ("signal_engine.decision_policy.setup_regime_policy.*", "categorical_setup_regime_policy_not_numeric_tunable"),
    ("signal_engine.decision_policy.setup_regime_policy.*.*", "categorical_setup_regime_policy_not_numeric_tunable"),
    ("risk_engine", "container_path_not_patchable"),
    ("risk_engine.gates", "container_path_not_patchable"),
    ("market_context_engine", "container_path_not_patchable"),
    ("setup_targets", "container_path_not_patchable"),
    ("swing_backtest.attribution.score_buckets", "container_path_not_patchable"),
    ("setups.*.gates.required_trend", "categorical_setup_gate_not_numeric_tunable"),
    ("setups.*.gates.reject_smart_net_selling", "boolean_setup_gate_not_numeric_tunable"),
    ("setup_phase.rs_policy_by_setup_family.*.warning_max_decision", "categorical_rs_policy_not_numeric_tunable"),
    ("setup_phase.rs_policy_by_setup_family.*.hard_exclude_max_decision", "categorical_rs_policy_not_numeric_tunable"),
    ("setup_phase.rs_policy_by_setup_family.*.mean_reversion_exception_requires_support_reclaim", "boolean_rs_policy_not_numeric_tunable"),
    ("setup_phase.volume_trigger.require_trusted_volume", "boolean_volume_policy_not_numeric_tunable"),
    ("setup_phase.volume_trigger.trusted_benchmark_volume_sources", "list_volume_policy_not_numeric_tunable"),
    ("setup_phase.volume_trigger.dry_up_lookback_sessions", "window_size_not_numeric_tunable"),
    ("setup_phase.volume_trigger.dry_up_reference_sessions", "window_size_not_numeric_tunable"),
    ("setup_phase.volume_trigger.expansion_requires_positive_close", "boolean_volume_policy_not_numeric_tunable"),
    # Point 3: superseded by volume_trigger.dry_up_max_ratio / expansion_min_ratio.
    # No longer read by _constructive_phase() — patching it would have zero
    # behavioral effect, so it must not be patch-eligible.
    ("setup_phase.thresholds.breakout_min_volume_ratio", "superseded_by_volume_trigger_policy"),
    # Evidence authority (DIAGNOSTIC/LOW_WEIGHT/PRODUCTION) and its promotion
    # record are a manual-review guardrail (see bootstrap._validate_promotion_record),
    # not a walk-forward tuning target. A tuning patch must never silently
    # promote diagnostic evidence into scoring authority.
    ("signal_engine.alpha_trigger.evidence_registrations.*.status", "evidence_authority_promotion_requires_manual_review"),
    ("signal_engine.alpha_trigger.evidence_registrations.*.promotion", "evidence_authority_promotion_requires_manual_review"),
    ("signal_engine.alpha_trigger.evidence_registrations.*.promotion.*", "evidence_authority_promotion_requires_manual_review"),
)


def _bounds_for_document_path(
    document_path: str,
) -> tuple[float, float, float | None, float] | None:
    """Return (min, max, step, max_shift) if document_path matches a bounds policy.

    Patterns containing '*' are matched with fnmatch; others require exact equality.
    """
    for pattern, lo, hi, step, max_shift in _PARAMETER_BOUNDS:
        match = (
            fnmatch(document_path, pattern) if "*" in pattern
            else document_path == pattern
        )
        if match:
            return (lo, hi, step, max_shift)
    return None


def _non_tunable_reason_for_document_path(document_path: str) -> str | None:
    for pattern, reason in _NON_TUNABLE_DOCUMENT_PATHS:
        match = (
            fnmatch(document_path, pattern) if "*" in pattern
            else document_path == pattern
        )
        if match:
            return reason
    return None


def _is_quantized(value: float, step: float) -> bool:
    """True when value is a multiple of step within floating-point tolerance."""
    if step <= 0:
        return True
    remainder = abs(value % step)
    return remainder < 1e-9 or abs(remainder - step) < 1e-9


@dataclass(frozen=True)
class SwingTuningPatchItemValidation:
    target_path: str | None
    valid: bool
    current_value: object | None
    proposed_value: object | None
    issues: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "valid": self.valid,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class SwingTuningPatchValidationReport:
    patch_path: str
    valid: bool
    artifact_type: str | None
    item_count: int
    valid_item_count: int
    issues: tuple[str, ...]
    item_results: tuple[SwingTuningPatchItemValidation, ...]

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "valid": self.valid,
            "artifact_type": self.artifact_type,
            "item_count": self.item_count,
            "valid_item_count": self.valid_item_count,
            "issues": list(self.issues),
            "item_results": [item.to_dict() for item in self.item_results],
        }


@dataclass(frozen=True)
class SwingTuningPatchDryRunChange:
    target_path: str
    current_value: object | None
    proposed_value: object | None

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
        }


@dataclass(frozen=True)
class SwingTuningPatchDryRunReport:
    patch_path: str
    ready: bool
    validation: SwingTuningPatchValidationReport
    changes: tuple[SwingTuningPatchDryRunChange, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "ready": self.ready,
            "validation": self.validation.to_dict(),
            "changes": [change.to_dict() for change in self.changes],
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class SwingTuningPatchApplyChange:
    target_path: str
    file_path: str
    document_path: str
    old_value: object | None
    new_value: object | None

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "file_path": self.file_path,
            "document_path": self.document_path,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


@dataclass(frozen=True)
class SwingTuningPatchApplyReport:
    patch_path: str
    applied: bool
    dry_run: SwingTuningPatchDryRunReport
    changes: tuple[SwingTuningPatchApplyChange, ...]
    issues: tuple[str, ...]
    log_path: str | None
    applied_at: str | None

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "applied": self.applied,
            "dry_run": self.dry_run.to_dict(),
            "changes": [change.to_dict() for change in self.changes],
            "issues": list(self.issues),
            "log_path": self.log_path,
            "applied_at": self.applied_at,
        }


@dataclass(frozen=True)
class SwingTuningPatchVerifyItem:
    target_path: str | None
    verified: bool
    expected_value: object | None
    actual_value: object | None
    issues: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path,
            "verified": self.verified,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "issues": list(self.issues),
        }


@dataclass(frozen=True)
class SwingTuningPatchVerifyReport:
    patch_path: str
    verified: bool
    artifact_type: str | None
    item_count: int
    verified_item_count: int
    issues: tuple[str, ...]
    item_results: tuple[SwingTuningPatchVerifyItem, ...]

    def to_dict(self) -> dict:
        return {
            "patch_path": self.patch_path,
            "verified": self.verified,
            "artifact_type": self.artifact_type,
            "item_count": self.item_count,
            "verified_item_count": self.verified_item_count,
            "issues": list(self.issues),
            "item_results": [item.to_dict() for item in self.item_results],
        }


class SwingTuningPatchValidator:
    def __init__(self, config_root: Path | str = Path(".")) -> None:
        self._config_root = Path(config_root)

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
            self._validate_item(item, seen_paths=seen_paths)
            for item in patch_items
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
                    non_tunable_reason = _non_tunable_reason_for_document_path(
                        document_path
                    )
                    if non_tunable_reason is not None:
                        item_issues.append(
                            f"target_path_not_tunable:{non_tunable_reason}"
                        )
                    resolution = resolve_tuning_config_value(
                        parsed,
                        config_root=self._config_root,
                    )
                    if not resolution.resolved:
                        item_issues.append(
                            f"target_path_unresolved:{resolution.unresolved_reason}"
                        )
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
                        item_issues.append(
                            f"proposed_value_exceeds_shift_cap:{max_shift}"
                        )

        return SwingTuningPatchItemValidation(
            target_path=target_path,
            valid=not item_issues,
            current_value=resolved_current_value,
            proposed_value=proposed_value,
            issues=tuple(item_issues),
        )


class SwingTuningPatchDryRunPlanner:
    def __init__(self, config_root: Path | str = Path(".")) -> None:
        self._validator = SwingTuningPatchValidator(config_root=config_root)

    def plan(self, patch_path: Path) -> SwingTuningPatchDryRunReport:
        validation = self._validator.validate(patch_path)
        issues: list[str] = []
        if not validation.valid:
            issues.append("patch_validation_failed")
        if validation.item_count == 0:
            issues.append("patch_has_no_items")

        changes = tuple(
            SwingTuningPatchDryRunChange(
                target_path=item.target_path or "",
                current_value=item.current_value,
                proposed_value=item.proposed_value,
            )
            for item in validation.item_results
            if item.valid and item.target_path
        )
        ready = not issues and bool(changes)
        return SwingTuningPatchDryRunReport(
            patch_path=str(patch_path),
            ready=ready,
            validation=validation,
            changes=changes,
            issues=tuple(issues),
        )


class SwingTuningPatchApplier:
    def __init__(
        self,
        config_root: Path | str = Path("."),
        *,
        target_dirty_checker: TargetDirtyChecker | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config_root = Path(config_root)
        self._planner = SwingTuningPatchDryRunPlanner(config_root=config_root)
        self._target_dirty_checker = target_dirty_checker or (lambda _path: False)
        self._clock = clock or datetime.now

    def apply(
        self,
        patch_path: Path,
        *,
        confirmed: bool,
        log_path: Path | None = None,
    ) -> SwingTuningPatchApplyReport:
        dry_run = self._planner.plan(patch_path)
        issues: list[str] = []
        if not confirmed:
            issues.append("apply_confirmation_required")
        if not dry_run.ready:
            issues.append("dry_run_not_ready")

        changes = self._build_changes(dry_run)
        target_files = tuple(dict.fromkeys(change.file_path for change in changes))
        for target_file in target_files:
            full_path = self._resolve_target_file(target_file)
            if self._target_dirty_checker(full_path):
                issues.append(f"target_config_dirty:{target_file}")

        if issues:
            return SwingTuningPatchApplyReport(
                patch_path=str(patch_path),
                applied=False,
                dry_run=dry_run,
                changes=changes,
                issues=tuple(issues),
                log_path=str(log_path) if log_path else None,
                applied_at=None,
            )

        for target_file in target_files:
            file_changes = tuple(
                change for change in changes if change.file_path == target_file
            )
            self._apply_file_changes(target_file, file_changes)

        applied_at = self._clock().isoformat()
        if log_path is not None:
            self._append_log(
                log_path,
                patch_path=patch_path,
                applied_at=applied_at,
                changes=changes,
            )

        return SwingTuningPatchApplyReport(
            patch_path=str(patch_path),
            applied=True,
            dry_run=dry_run,
            changes=changes,
            issues=(),
            log_path=str(log_path) if log_path else None,
            applied_at=applied_at,
        )

    def _build_changes(
        self,
        dry_run: SwingTuningPatchDryRunReport,
    ) -> tuple[SwingTuningPatchApplyChange, ...]:
        changes: list[SwingTuningPatchApplyChange] = []
        for change in dry_run.changes:
            parsed = parse_tuning_config_path(change.target_path)
            changes.append(
                SwingTuningPatchApplyChange(
                    target_path=change.target_path,
                    file_path=parsed.file_path,
                    document_path=parsed.document_path,
                    old_value=change.current_value,
                    new_value=change.proposed_value,
                )
            )
        return tuple(changes)

    def _apply_file_changes(
        self,
        file_path: str,
        changes: tuple[SwingTuningPatchApplyChange, ...],
    ) -> None:
        full_path = self._resolve_target_file(file_path)
        with full_path.open(encoding="utf-8") as fh:
            document = yaml.safe_load(fh) or {}
        if not isinstance(document, dict):
            raise ValueError(f"YAML document must be a mapping: {file_path}")

        for change in changes:
            _set_document_value(document, change.document_path, change.new_value)

        with full_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(
                document,
                fh,
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )

    def _resolve_target_file(self, file_path: str) -> Path:
        root = self._config_root.resolve()
        full_path = (root / file_path).resolve()
        if full_path != root and root not in full_path.parents:
            raise ValueError(f"Tuning target escapes config root: {file_path}")
        return full_path

    def _append_log(
        self,
        log_path: Path,
        *,
        patch_path: Path,
        applied_at: str,
        changes: tuple[SwingTuningPatchApplyChange, ...],
    ) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "artifact_type": "swing_tuning_patch_apply",
            "applied_at": applied_at,
            "patch_path": str(patch_path),
            "changes": [change.to_dict() for change in changes],
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str))
            fh.write("\n")


class SwingTuningPatchVerifier:
    def __init__(self, config_root: Path | str = Path(".")) -> None:
        self._config_root = Path(config_root)

    def verify(self, patch_path: Path) -> SwingTuningPatchVerifyReport:
        try:
            payload = json.loads(patch_path.read_text())
        except FileNotFoundError:
            return _invalid_verify_report(str(patch_path), "patch_file_not_found")
        except json.JSONDecodeError:
            return _invalid_verify_report(str(patch_path), "patch_json_invalid")

        issues: list[str] = []
        artifact_type = _str(payload.get("artifact_type"))
        if artifact_type != "swing_tuning_patch_review":
            issues.append("artifact_type_must_be_swing_tuning_patch_review")

        apply_block = payload.get("apply")
        if not isinstance(apply_block, dict) or apply_block.get("supported") is not False:
            issues.append("apply_supported_must_be_false")

        patch_items = payload.get("patch_items")
        if not isinstance(patch_items, list):
            issues.append("patch_items_must_be_list")
            patch_items = []

        seen_paths: set[str] = set()
        item_results = tuple(
            self._verify_item(item, seen_paths=seen_paths) for item in patch_items
        )
        verified = (
            not issues
            and bool(item_results)
            and all(item.verified for item in item_results)
        )
        if not item_results:
            issues.append("patch_has_no_items")

        return SwingTuningPatchVerifyReport(
            patch_path=str(patch_path),
            verified=verified,
            artifact_type=artifact_type,
            item_count=len(patch_items),
            verified_item_count=sum(1 for item in item_results if item.verified),
            issues=tuple(issues),
            item_results=item_results,
        )

    def _verify_item(
        self,
        item: object,
        seen_paths: set[str],
    ) -> SwingTuningPatchVerifyItem:
        item_issues: list[str] = []
        item_dict = item if isinstance(item, dict) else {}
        if not item_dict:
            item_issues.append("patch_item_must_be_object")

        target_path = _str(item_dict.get("target_path"))
        proposed_value = item_dict.get("proposed_value")
        actual_value: object | None = None

        if not target_path:
            item_issues.append("target_path_required")
        elif target_path in seen_paths:
            item_issues.append("duplicate_target_path")
        else:
            seen_paths.add(target_path)

        if proposed_value is None:
            item_issues.append("proposed_value_required")

        if target_path:
            try:
                parsed = parse_tuning_config_path(target_path)
            except ValueError:
                item_issues.append("target_path_invalid")
            else:
                resolution = resolve_tuning_config_value(
                    parsed,
                    config_root=self._config_root,
                )
                if not resolution.resolved:
                    item_issues.append(
                        f"target_path_unresolved:{resolution.unresolved_reason}"
                    )
                else:
                    actual_value = resolution.current_value
                    if actual_value != proposed_value:
                        item_issues.append("proposed_value_not_applied")

        return SwingTuningPatchVerifyItem(
            target_path=target_path,
            verified=not item_issues,
            expected_value=proposed_value,
            actual_value=actual_value,
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
            issues.append(f"{prefix} oos_backtest_summary.total_return_pct is required (may be null)")
        if "win_rate_pct" not in oos:
            issues.append(f"{prefix} oos_backtest_summary.win_rate_pct is required (may be null)")
    return tuple(issues)


def _validate_sample_readiness(source_review: object) -> tuple[str, ...]:
    """Return issue strings when sample quality is insufficient for apply.

    All issues are prefixed with 'sample_not_ready:' so callers can detect
    the category with a single substring check.

    The validator is closed-by-default: missing required fields are rejected,
    not skipped. Phase I separates diagnostic-ready report output from
    patch-eligible config mutation. This validator only accepts patch-eligible
    source reviews.
    """
    prefix = "sample_not_ready:"
    issues: list[str] = []
    if not isinstance(source_review, dict):
        return ()  # structural error already reported by walk_forward check

    readiness_state = source_review.get("readiness_state")
    if readiness_state not in {"PATCH_ELIGIBLE", "patch_eligible"}:
        issues.append(
            f"{prefix} readiness_state must be PATCH_ELIGIBLE for config patch "
            f"validation; got {readiness_state!r}. Diagnostic-ready output is report-only."
        )

    # IS sample quality — source summary must still be coherent, but the
    # authoritative threshold is the canonical Phase I trade count below.
    sample = source_review.get("sample")
    if not isinstance(sample, dict):
        issues.append(f"{prefix} source_review.sample must be a dict")
    else:
        status = sample.get("status")
        if status not in {"TRADE_READY", "MIXED_READY"}:
            issues.append(
                f"{prefix} sample.status must be TRADE_READY or MIXED_READY, "
                f"got {status!r}; need patch-eligible IS/OOS evidence"
            )

    backtest = source_review.get("backtest_summary")
    if not isinstance(backtest, dict):
        issues.append(f"{prefix} source_review.backtest_summary must be a dict")
    else:
        try:
            is_trades = int(backtest.get("trade_count"))  # type: ignore[arg-type]
            if is_trades < _PATCH_MIN_IS_TRADE_COUNT:
                issues.append(
                    f"{prefix} IS completed_trade_count={is_trades} "
                    f"< {_PATCH_MIN_IS_TRADE_COUNT}"
                )
        except (TypeError, ValueError):
            issues.append(f"{prefix} backtest_summary.trade_count is missing or non-integer")

    # OOS quality — diagnostic-ready is report-only; config patches require the
    # stricter canonical patch-eligible OOS sample and performance floors.
    oos = source_review.get("oos_backtest_summary")
    if isinstance(oos, dict):
        oos_trades: int | None = None
        try:
            oos_trades = int(oos.get("trade_count"))  # type: ignore[arg-type]
            if oos_trades < _DIAGNOSTIC_MIN_OOS_TRADE_COUNT:
                issues.append(
                    f"{prefix} OOS trade_count={oos_trades} "
                    f"< diagnostic-ready minimum {_DIAGNOSTIC_MIN_OOS_TRADE_COUNT}"
                )
            elif oos_trades < _PATCH_MIN_OOS_TRADE_COUNT:
                issues.append(
                    f"{prefix} OOS trade_count={oos_trades} "
                    f"< patch-eligible minimum {_PATCH_MIN_OOS_TRADE_COUNT}; "
                    "diagnostic-ready output is report-only"
                )
        except (TypeError, ValueError):
            issues.append(f"{prefix} oos_backtest_summary.trade_count is missing or non-integer")

        if oos_trades is not None and oos_trades >= _DIAGNOSTIC_MIN_OOS_TRADE_COUNT:
            profit_factor = _float_field(oos, "profit_factor")
            if profit_factor is None:
                issues.append(f"{prefix} OOS profit_factor must be numeric")
            elif profit_factor < _PATCH_MIN_OOS_PROFIT_FACTOR:
                issues.append(
                    f"{prefix} OOS profit_factor={profit_factor} "
                    f"< floor {_PATCH_MIN_OOS_PROFIT_FACTOR}"
                )

            average_return = _first_float_field(
                oos,
                ("average_return_pct", "avg_return_pct"),
            )
            if average_return is None:
                issues.append(
                    f"{prefix} OOS average_return_pct must be numeric"
                )
            elif average_return < _PATCH_MIN_OOS_AVERAGE_RETURN_PCT:
                issues.append(
                    f"{prefix} OOS average_return_pct={average_return} "
                    f"< floor {_PATCH_MIN_OOS_AVERAGE_RETURN_PCT}"
                )

            drawdown_regression = _first_float_field(
                oos,
                ("drawdown_regression_pct", "max_drawdown_regression"),
            )
            if drawdown_regression is None:
                issues.append(
                    f"{prefix} OOS drawdown_regression_pct must be numeric"
                )
            elif drawdown_regression > _PATCH_MAX_OOS_DRAWDOWN_REGRESSION:
                issues.append(
                    f"{prefix} OOS drawdown_regression_pct={drawdown_regression} "
                    f"> max {_PATCH_MAX_OOS_DRAWDOWN_REGRESSION}"
                )
    else:
        issues.append(f"{prefix} source_review.oos_backtest_summary must be a dict")

    issues.extend(_validate_attribution_readiness(source_review, prefix=prefix))

    return tuple(issues)


def _float_field(payload: dict, field: str) -> float | None:
    try:
        return float(payload.get(field))
    except (TypeError, ValueError):
        return None


def _first_float_field(payload: dict, fields: tuple[str, ...]) -> float | None:
    for field in fields:
        value = _float_field(payload, field)
        if value is not None:
            return value
    return None


def _validate_attribution_readiness(
    source_review: dict,
    *,
    prefix: str,
) -> tuple[str, ...]:
    issues: list[str] = []
    attribution = source_review.get("attribution")
    if not isinstance(attribution, dict):
        return (f"{prefix} source_review.attribution must be a dict",)

    for group in ("market_regime", "coverage_bucket", "conviction_bucket"):
        buckets = _attribution_buckets(attribution.get(group))
        if not buckets:
            issues.append(f"{prefix} attribution.{group} must include buckets")

    if source_review.get("single_regime_scoped") is True:
        return tuple(issues)

    regime_buckets = _attribution_buckets(attribution.get("market_regime"))
    positive_profit_rows = [
        row for row in regime_buckets
        if _first_float_field(row, ("oos_profit", "total_pnl", "profit")) is not None
        and (_first_float_field(row, ("oos_profit", "total_pnl", "profit")) or 0.0) > 0.0
    ]
    positive_profit = sum(
        _first_float_field(row, ("oos_profit", "total_pnl", "profit")) or 0.0
        for row in positive_profit_rows
    )
    if positive_profit > 0.0:
        max_share = max(
            (
                (_first_float_field(row, ("oos_profit", "total_pnl", "profit")) or 0.0)
                / positive_profit
            )
            for row in positive_profit_rows
        )
        if max_share > _MAX_SINGLE_REGIME_OOS_PROFIT_SHARE:
            issues.append(
                f"{prefix} single-regime OOS profit share={max_share:.4f} "
                f"> {_MAX_SINGLE_REGIME_OOS_PROFIT_SHARE}"
            )

    counted_positive_regimes = 0
    for row in regime_buckets:
        profit = _first_float_field(row, ("oos_profit", "total_pnl", "profit"))
        trade_count = _first_float_field(row, ("oos_trade_count", "trade_count"))
        if (
            profit is not None
            and profit > 0.0
            and trade_count is not None
            and trade_count >= _MIN_OOS_TRADES_PER_COUNTED_REGIME
        ):
            counted_positive_regimes += 1
    if counted_positive_regimes < _MIN_POSITIVE_OOS_REGIME_COUNT:
        issues.append(
            f"{prefix} positive OOS regime count={counted_positive_regimes} "
            f"< {_MIN_POSITIVE_OOS_REGIME_COUNT}"
        )

    return tuple(issues)


def _attribution_buckets(value: object) -> tuple[dict, ...]:
    if isinstance(value, dict):
        buckets = value.get("buckets")
        if isinstance(buckets, list):
            return tuple(row for row in buckets if isinstance(row, dict))
        if all(isinstance(row, dict) for row in value.values()):
            return tuple(value.values())
    if isinstance(value, list):
        return tuple(row for row in value if isinstance(row, dict))
    return ()


def _invalid_report(patch_path: str, issue: str) -> SwingTuningPatchValidationReport:
    return SwingTuningPatchValidationReport(
        patch_path=patch_path,
        valid=False,
        artifact_type=None,
        item_count=0,
        valid_item_count=0,
        issues=(issue,),
        item_results=(),
    )


def _invalid_verify_report(patch_path: str, issue: str) -> SwingTuningPatchVerifyReport:
    return SwingTuningPatchVerifyReport(
        patch_path=patch_path,
        verified=False,
        artifact_type=None,
        item_count=0,
        verified_item_count=0,
        issues=(issue,),
        item_results=(),
    )


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
        return (
            isinstance(proposed_value, int | float)
            and not isinstance(proposed_value, bool)
        )
    if isinstance(current_value, str):
        return isinstance(proposed_value, str)
    return type(proposed_value) is type(current_value)


def _set_document_value(
    document: dict,
    document_path: str,
    value: object | None,
) -> None:
    current: object = document
    parts = document_path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"YAML document path not found: {document_path}")
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        raise ValueError(f"YAML document path not found: {document_path}")
    current[parts[-1]] = value
