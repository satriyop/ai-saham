"""Swing tuning config path helper tests.

These tests own read-only YAML tuning path parsing, wildcard expansion,
validation, and value resolution behavior.
"""

import pytest

from src.application.services.swing_backtest_attribution import (
    summarize_swing_backtest_attribution,
)
from src.application.services.swing_tuning_config_paths import (
    expand_tuning_config_paths,
    parse_tuning_config_path,
    resolve_tuning_config_value,
    validate_tuning_target_paths,
)


def test_parse_tuning_config_path_splits_file_and_document_path():
    parsed = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.classification"
    )

    assert parsed.raw == "config/signal_engine.yaml:signal_engine.classification"
    assert parsed.file_path == "config/signal_engine.yaml"
    assert parsed.document_path == "signal_engine.classification"
    assert parsed.to_dict() == {
        "raw": "config/signal_engine.yaml:signal_engine.classification",
        "file_path": "config/signal_engine.yaml",
        "document_path": "signal_engine.classification",
    }


@pytest.mark.parametrize(
    "raw_path",
    (
        "config/signal_engine.yaml",
        "config/signal_engine.yaml:",
        ":signal_engine.classification",
        "config/signal_engine.json:signal_engine.classification",
    ),
)
def test_parse_tuning_config_path_rejects_invalid_format(raw_path):
    with pytest.raises(ValueError):
        parse_tuning_config_path(raw_path)


def test_resolve_tuning_config_value_reads_concrete_yaml_path(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 70\n",
        encoding="utf-8",
    )
    parsed = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
    )

    resolution = resolve_tuning_config_value(parsed, config_root=tmp_path)

    assert resolution.resolved is True
    assert resolution.current_value == 70
    assert resolution.unresolved_reason is None
    assert resolution.to_dict()["current_value"] == 70


def test_resolve_tuning_config_value_reports_missing_config_file(tmp_path):
    parsed = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
    )

    resolution = resolve_tuning_config_value(parsed, config_root=tmp_path)

    assert resolution.resolved is False
    assert resolution.current_value is None
    assert resolution.unresolved_reason == "config_file_not_found"


def test_resolve_tuning_config_value_reports_missing_document_path(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification: {}\n",
        encoding="utf-8",
    )
    parsed = parse_tuning_config_path(
        "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
    )

    resolution = resolve_tuning_config_value(parsed, config_root=tmp_path)

    assert resolution.resolved is False
    assert resolution.current_value is None
    assert resolution.unresolved_reason == "document_path_not_found"


def test_resolve_tuning_config_value_rejects_wildcard_without_reading_yaml(tmp_path):
    parsed = parse_tuning_config_path("config/swing_setups.yaml:setups.*.gates")

    resolution = resolve_tuning_config_value(parsed, config_root=tmp_path)

    assert resolution.resolved is False
    assert resolution.current_value is None
    assert resolution.unresolved_reason == "wildcard_path_not_resolved"


def test_expand_tuning_config_paths_expands_allowlisted_setup_wildcards(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "swing_setups.yaml").write_text(
        "setups:\n"
        "  foreign-bounce:\n"
        "    gates:\n"
        "      min_foreign_flow_score: 70\n"
        "      required_trend: SIDE\n"
        "    partial_max_failed_gates: 2\n",
        encoding="utf-8",
    )

    gate_paths = expand_tuning_config_paths(
        "config/swing_setups.yaml:setups.*.gates",
        config_root=tmp_path,
    )
    partial_paths = expand_tuning_config_paths(
        "config/swing_setups.yaml:setups.*.partial_max_failed_gates",
        config_root=tmp_path,
    )

    assert gate_paths == (
        "config/swing_setups.yaml:setups.foreign-bounce.gates.min_foreign_flow_score",
        "config/swing_setups.yaml:setups.foreign-bounce.gates.required_trend",
    )
    assert partial_paths == (
        "config/swing_setups.yaml:setups.foreign-bounce.partial_max_failed_gates",
    )


def test_expand_tuning_config_paths_leaves_unknown_wildcards_unexpanded():
    raw_path = "config/risk_engine.yaml:risk_engine.gates.*.enabled"

    assert expand_tuning_config_paths(raw_path) == (raw_path,)


def test_validate_tuning_target_paths_covers_all_current_targets():
    summary = summarize_swing_backtest_attribution(())

    parsed_paths = validate_tuning_target_paths(summary)

    assert parsed_paths == tuple(
        yaml_path
        for target in summary.tuning_targets
        for yaml_path in target.yaml_paths
    )


def _write_two_setup_yaml(config_dir) -> None:
    (config_dir / "swing_setups.yaml").write_text(
        "setups:\n"
        "  foreign-bounce:\n"
        "    gates:\n"
        "      min_foreign_flow_score: 70\n"
        "    partial_max_failed_gates: 2\n"
        "  coiled-spring:\n"
        "    gates:\n"
        "      max_bb_width_pctile: 0.20\n"
        "    partial_max_failed_gates: 2\n",
        encoding="utf-8",
    )


def test_active_setups_gate_filter_returns_only_matching_setup(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_two_setup_yaml(config_dir)

    gate_paths = expand_tuning_config_paths(
        "config/swing_setups.yaml:setups.*.gates",
        config_root=tmp_path,
        active_setups=frozenset({"foreign-bounce"}),
    )
    partial_paths = expand_tuning_config_paths(
        "config/swing_setups.yaml:setups.*.partial_max_failed_gates",
        config_root=tmp_path,
        active_setups=frozenset({"foreign-bounce"}),
    )

    assert gate_paths == (
        "config/swing_setups.yaml:setups.foreign-bounce.gates.min_foreign_flow_score",
    )
    assert partial_paths == (
        "config/swing_setups.yaml:setups.foreign-bounce.partial_max_failed_gates",
    )


def test_active_setups_unknown_setup_returns_empty(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_two_setup_yaml(config_dir)

    gate_paths = expand_tuning_config_paths(
        "config/swing_setups.yaml:setups.*.gates",
        config_root=tmp_path,
        active_setups=frozenset({"does-not-exist"}),
    )
    partial_paths = expand_tuning_config_paths(
        "config/swing_setups.yaml:setups.*.partial_max_failed_gates",
        config_root=tmp_path,
        active_setups=frozenset({"does-not-exist"}),
    )

    assert gate_paths == ()
    assert partial_paths == ()


def test_no_active_setups_preserves_all_setup_expansion(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_two_setup_yaml(config_dir)

    gate_paths = expand_tuning_config_paths(
        "config/swing_setups.yaml:setups.*.gates",
        config_root=tmp_path,
    )

    assert (
        "config/swing_setups.yaml:setups.foreign-bounce.gates.min_foreign_flow_score"
        in gate_paths
    )
    assert (
        "config/swing_setups.yaml:setups.coiled-spring.gates.max_bb_width_pctile"
        in gate_paths
    )
