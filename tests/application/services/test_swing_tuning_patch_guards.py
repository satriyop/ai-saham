"""Patch level guardrail and non-tunable target tests for swing tuning."""

import json

from src.application.services.swing_tuning_patch_validation import (
    _bounds_for_document_path,
    _non_tunable_reason_for_document_path,
)
from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchValidator,
)
from tests.application.services.swing_tuning_guardrail_fixtures import (
    _COMPLETE_SOURCE_REVIEW,
    _STRONG_PATH,
    _target_by_dimension,
    _validate_single,
    _write_config,
)


def test_unbounded_resolved_numeric_path_fails_closed(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n  experimental:\n    loose_threshold: 1.0\n",
        encoding="utf-8",
    )
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": _COMPLETE_SOURCE_REVIEW,
                "patch_items": [
                    {
                        "target_path": (
                            "config/signal_engine.yaml:signal_engine.experimental.loose_threshold"
                        ),
                        "current_value": 1.0,
                        "proposed_value": 1.1,
                    },
                ],
            }
        )
    )

    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)

    assert report.valid is False
    assert "target_path_unbounded" in report.item_results[0].issues


def test_shift_cap_rejects_large_weight_change(tmp_path):
    from tests.application.services.swing_tuning_guardrail_fixtures import _WEIGHT_PATH
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.80)
    assert result.valid is False
    assert any("exceeds_shift_cap" in issue for issue in result.issues)


def test_shift_cap_accepts_small_weight_change(tmp_path):
    from tests.application.services.swing_tuning_guardrail_fixtures import _WEIGHT_PATH
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.65)
    assert result.valid is True
    assert result.issues == ()


def test_shift_cap_accepts_score_change_within_cap(tmp_path):
    result = _validate_single(tmp_path, _STRONG_PATH, 70, 74)
    assert result.valid is True
    assert result.issues == ()


def test_shift_cap_rejects_score_change_over_cap(tmp_path):
    result = _validate_single(tmp_path, _STRONG_PATH, 70, 76)
    assert result.valid is False
    assert any("exceeds_shift_cap" in issue for issue in result.issues)


def test_regime_target_excludes_regime_conditioning_paths():
    """regime_conditioning is frozen (TD-1) — must not appear in tunable yaml_paths."""
    regime = _target_by_dimension("regime")
    conditioning_paths = [p for p in regime.yaml_paths if "regime_conditioning" in p]
    assert conditioning_paths == [], (
        f"regime_conditioning paths must not be tunable: {conditioning_paths}"
    )


def test_patch_modifying_regime_conditioning_fails(tmp_path):
    """Explicitly test that target paths containing 'regime_conditioning'
    are blocked by validator.
    """
    result = _validate_single(
        tmp_path,
        "signal_engine.regime_conditioning.neutral.weak_flow_discount",
        0.80,
        0.75,
    )
    assert result.valid is False
    assert "target_path_not_tunable:regime_conditioning_is_legacy_layer" in result.issues


def test_patch_changing_evidence_registration_status_rejected(tmp_path):
    """Evidence authority (DIAGNOSTIC/LOW_WEIGHT/PRODUCTION) must never be
    promoted by the tuning system — only a manual promotion record review."""
    result = _validate_single(
        tmp_path,
        "signal_engine.alpha_trigger.evidence_registrations.market_context.status",
        "DIAGNOSTIC",
        "LOW_WEIGHT",
    )
    assert result.valid is False
    assert (
        "target_path_not_tunable:evidence_authority_promotion_requires_manual_review"
        in result.issues
    )


def test_patch_changing_evidence_promotion_record_rejected(tmp_path):
    """A patch must not silently attach/alter a promotion record either —
    promotion is a manual-review artifact, not a tuning-diff target."""
    result = _validate_single(
        tmp_path,
        "signal_engine.alpha_trigger.evidence_registrations.market_context.promotion.promoted_to",
        "DIAGNOSTIC",
        "LOW_WEIGHT",
    )
    assert result.valid is False
    assert (
        "target_path_not_tunable:evidence_authority_promotion_requires_manual_review"
        in result.issues
    )


def test_breakout_min_volume_ratio_bounds_lookup_returns_none():
    """Superseded by volume_trigger.dry_up_max_ratio/expansion_min_ratio (Point
    3) — must not resolve to numeric bounds, else it would look tunable."""
    assert _bounds_for_document_path("setup_phase.thresholds.breakout_min_volume_ratio") is None


def test_breakout_min_volume_ratio_non_tunable_reason_declared():
    assert (
        _non_tunable_reason_for_document_path("setup_phase.thresholds.breakout_min_volume_ratio")
        == "superseded_by_volume_trigger_policy"
    )


def test_patch_modifying_breakout_min_volume_ratio_fails(tmp_path):
    """No longer read by _constructive_phase() — a patch against it would have
    zero behavioral effect, so the validator must reject it, not silently
    accept a no-op tuning proposal."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "swing_setups.yaml").write_text(
        "setup_phase:\n  thresholds:\n    breakout_min_volume_ratio: 1.20\n",
        encoding="utf-8",
    )
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": _COMPLETE_SOURCE_REVIEW,
                "patch_items": [
                    {
                        "target_path": (
                            "config/swing_setups.yaml:"
                            "setup_phase.thresholds.breakout_min_volume_ratio"
                        ),
                        "current_value": 1.20,
                        "proposed_value": 1.50,
                    },
                ],
            }
        )
    )
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    result = report.item_results[0]

    assert result.valid is False
    assert "target_path_not_tunable:superseded_by_volume_trigger_policy" in result.issues


def test_signal_strength_target_includes_enter_min_confidence_path():
    signal_strength = _target_by_dimension("signal_strength")
    assert (
        "config/signal_engine.yaml:signal_engine.classification.enter_min_confidence"
        in signal_strength.yaml_paths
    )


def test_patch_without_source_review_fails_validation(tmp_path):
    # Patches with no source_review (legacy or bypassed format) must fail: there
    # is no provenance guarantee that proposals came from IS data only.
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "patch_items": [],
            }
        )
    )
    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)
