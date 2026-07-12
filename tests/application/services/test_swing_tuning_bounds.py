"""Bounds, range, and quantization enforcement tests for swing tuning."""

from src.application.services.swing_backtest_attribution import (
    DEFAULT_TUNING_TARGETS,
)
from src.application.services.swing_tuning_config_paths import (
    expand_tuning_config_paths,
    parse_tuning_config_path,
)
from src.application.services.swing_tuning_patch_validation import (
    _bounds_for_document_path,
    _is_quantized,
    _non_tunable_reason_for_document_path,
)
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)
from tests.application.services.swing_tuning_guardrail_fixtures import (
    _WEIGHT_PATH,
    _validate_single,
)


def test_bounds_for_document_path_known_returns_bounds():
    bounds = _bounds_for_document_path(_WEIGHT_PATH)
    assert bounds == (0.05, 1.0, 0.05, 0.10)


def test_bounds_for_document_path_unknown_returns_none():
    assert _bounds_for_document_path("signal_engine.unknown.path") is None


def test_current_tuning_target_paths_are_bounded_or_explicitly_non_tunable():
    missing: list[str] = []
    for target in DEFAULT_TUNING_TARGETS:
        for raw_path in target.yaml_paths:
            for expanded_path in expand_tuning_config_paths(
                raw_path, document_loader=swing_tuning_document_loader()
            ):
                parsed = parse_tuning_config_path(expanded_path)
                bounded = _bounds_for_document_path(parsed.document_path) is not None
                non_tunable = (
                    _non_tunable_reason_for_document_path(parsed.document_path) is not None
                )
                if not bounded and not non_tunable:
                    missing.append(expanded_path)

    assert missing == []


def test_is_quantized_true_for_grid_value():
    assert _is_quantized(0.60, 0.05) is True


def test_is_quantized_false_for_off_grid_value():
    assert _is_quantized(0.63, 0.05) is False


def test_range_rejects_weight_above_max(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 1.5)
    assert result.valid is False
    assert any("out_of_range" in issue for issue in result.issues)


def test_range_rejects_weight_below_min(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.02)
    assert result.valid is False
    assert any("out_of_range" in issue for issue in result.issues)


def test_range_accepts_in_bounds_weight(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.60)
    assert result.valid is True
    assert result.issues == ()


def test_quantization_rejects_off_grid_weight(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.63)
    assert result.valid is False
    assert any("not_quantized" in issue for issue in result.issues)


def test_quantization_accepts_on_grid_weight(tmp_path):
    result = _validate_single(tmp_path, _WEIGHT_PATH, 0.60, 0.65)
    assert result.valid is True
    assert result.issues == ()
