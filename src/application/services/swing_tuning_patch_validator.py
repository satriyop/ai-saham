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


# Minimum sample-quality thresholds required before a patch may be applied.
# These mirror the TUNING_READINESS logic in swing_backtest_attribution.py;
# any patch that would not reach TRADE_READY status is blocked here too.
_MIN_IS_TRADE_COUNT: int = 30
_MIN_OOS_TRADE_COUNT: int = 5
_MAX_OOS_LOSS_PCT: float = -15.0     # OOS total return below this → reject
_MIN_OOS_WIN_RATE_PCT: float = 40.0  # OOS win rate below this → reject
_MIN_OOS_PROFIT_FACTOR: float = 1.0  # OOS PF below this → reject (PF < 1 = losing system)

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
    # regime_conditioning.* removed from tunable paths: transitional legacy layer (TD-1).
    # Patches targeting regime_conditioning.* will now be rejected as out-of-bounds.
    # --- swing_setups paths (fnmatch wildcard on setup name) ---
    ("setups.*.gates.max_bb_width_pctile", 0.05, 0.50, 0.05, 0.10),
    ("setups.*.gates.max_rsi", 25, 80, 1, 5),
    ("setups.*.gates.min_rsi", 15, 60, 1, 5),
    ("setups.*.gates.min_flow_ratio_pct", 0.5, 25.0, 0.5, 2.0),
    ("setups.*.gates.min_foreign_flow_score", 30, 90, 1, 5),
    ("setups.*.gates.min_vwap_discount_pct", -5.0, 15.0, 0.5, 1.5),
    ("setups.*.partial_max_failed_gates", 0, 5, 1, 1),
    # --- risk_engine gate paths ---
    ("risk_engine.gates.free_float.min_free_float_pct", 10.0, 25.0, 0.5, 2.0),
    ("risk_engine.gates.fundamental.piotroski_min", 1, 7, 1, 1),
    ("risk_engine.gates.liquidity.market_cap_floor_idr", 1e11, 5e12, 1e11, 5e11),
    ("risk_engine.gates.liquidity.median_tx_floor_idr", 1e9, 5e10, 1e9, 5e9),
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

        # Phase 8: parameter bounds — range, quantization, per-cycle shift cap.
        if resolved_current_value is not None and proposed_value is not None and not item_issues:
            bounds = _bounds_for_document_path(parsed.document_path)
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
    not skipped. OOS metrics must be numeric (not null) when OOS trade count
    meets the minimum — a patch with 5+ OOS trades but no measurable outcome
    cannot be approved.
    """
    prefix = "sample_not_ready:"
    issues: list[str] = []
    if not isinstance(source_review, dict):
        return ()  # structural error already reported by walk_forward check

    # IS sample quality — both fields are required (Finding 1)
    sample = source_review.get("sample")
    if not isinstance(sample, dict):
        issues.append(f"{prefix} source_review.sample must be a dict")
    else:
        status = sample.get("status")
        # TRADE_READY = IS trades >= 30 (candidate observations below minimum).
        # MIXED_READY = IS trades >= 30 AND candidate observations >= 30 — the
        # better state. Both satisfy the patch-apply requirement.
        if status not in {"TRADE_READY", "MIXED_READY"}:
            issues.append(
                f"{prefix} sample.status must be TRADE_READY or MIXED_READY, "
                f"got {status!r}; need at least {_MIN_IS_TRADE_COUNT} completed IS trades"
            )

    backtest = source_review.get("backtest_summary")
    if not isinstance(backtest, dict):
        issues.append(f"{prefix} source_review.backtest_summary must be a dict")
    else:
        try:
            is_trades = int(backtest.get("trade_count"))  # type: ignore[arg-type]
            if is_trades < _MIN_IS_TRADE_COUNT:
                issues.append(
                    f"{prefix} IS completed_trade_count={is_trades} < {_MIN_IS_TRADE_COUNT}"
                )
        except (TypeError, ValueError):
            issues.append(f"{prefix} backtest_summary.trade_count is missing or non-integer")

    # OOS quality — trade count checked first; metrics required when count passes (Findings 2+3)
    oos = source_review.get("oos_backtest_summary")
    if isinstance(oos, dict):
        oos_trades: int | None = None
        try:
            oos_trades = int(oos.get("trade_count"))  # type: ignore[arg-type]
            if oos_trades < _MIN_OOS_TRADE_COUNT:
                issues.append(
                    f"{prefix} OOS trade_count={oos_trades} < {_MIN_OOS_TRADE_COUNT}"
                )
        except (TypeError, ValueError):
            issues.append(f"{prefix} oos_backtest_summary.trade_count is missing or non-integer")

        if oos_trades is not None and oos_trades >= _MIN_OOS_TRADE_COUNT:
            # Metrics must be numeric (not null) when OOS has sufficient trades
            for field, floor in (
                ("total_return_pct", _MAX_OOS_LOSS_PCT),
                ("win_rate_pct", _MIN_OOS_WIN_RATE_PCT),
                ("profit_factor", _MIN_OOS_PROFIT_FACTOR),
            ):
                raw = oos.get(field)
                try:
                    fval = float(raw)  # raises on None or non-numeric
                    if fval < floor:
                        issues.append(
                            f"{prefix} OOS {field}={fval} < floor {floor}"
                        )
                except (TypeError, ValueError):
                    issues.append(
                        f"{prefix} OOS {field} must be numeric when "
                        f"oos_trade_count >= {_MIN_OOS_TRADE_COUNT}"
                    )

    return tuple(issues)


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
