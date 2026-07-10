"""Verifier for applied swing tuning patches.

Layer: Application
"""

from __future__ import annotations

import json
from pathlib import Path

from src.application.services.swing_tuning_config_paths import (
    parse_tuning_config_path,
    resolve_tuning_config_value,
)
from src.application.services.swing_tuning_patch_reports import (
    SwingTuningPatchVerifyItem,
    SwingTuningPatchVerifyReport,
    _invalid_verify_report,
)
from src.application.services.swing_tuning_patch_validation import _str


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
        item_results = tuple(self._verify_item(item, seen_paths=seen_paths) for item in patch_items)
        verified = not issues and bool(item_results) and all(item.verified for item in item_results)
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
                    item_issues.append(f"target_path_unresolved:{resolution.unresolved_reason}")
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
