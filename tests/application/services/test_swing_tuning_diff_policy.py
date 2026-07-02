"""Swing tuning diff policy helper tests.

These tests own deterministic dry-run value selection, target classification,
interpretation wording, summary counts, and review checklist behavior.
"""

from dataclasses import dataclass

from src.application.services.swing_tuning_config_paths import (
    TuningConfigPath,
    TuningConfigValueResolution,
)
from src.application.services.swing_tuning_diff_policy import (
    TuningTargetClassification,
    build_tuning_config_diff_review_checklist,
    build_tuning_config_diff_summary,
    suggest_tuning_value,
    tuning_config_diff_item_interpretation,
    tuning_config_diff_rejection_interpretation,
    value_selection_policy_for_rejection,
)


@dataclass(frozen=True)
class _Candidate:
    dimension: str
    evidence_strength: str
    evidence_buckets: tuple[str, ...]


@dataclass(frozen=True)
class _DiffItem:
    proposed_value: object | None
    value_selection_policy: str
    evidence_dimension: str = "signal_strength"
    evidence_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RejectedItem:
    value_selection_policy: str = "CONFIG_FILE_NOT_FOUND"


def _path(raw: str) -> TuningConfigPath:
    return TuningConfigPath(
        raw=raw,
        file_path=raw.split(":", maxsplit=1)[0],
        document_path=raw.split(":", maxsplit=1)[1],
    )


def test_target_classification_describes_signal_classification_threshold():
    classification = TuningTargetClassification.from_path(
        _path(
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
        )
    )

    assert classification.to_dict() == {
        "target_family": "signal_engine",
        "target_kind": "classification",
        "target_parameter": "strong_min_score",
    }


def test_target_classification_describes_setup_gate_and_unknown_path():
    gate = TuningTargetClassification.from_path(
        _path(
            "config/swing_setups.yaml:setups.foreign-bounce.gates.min_foreign_flow_score"
        )
    )
    unknown = TuningTargetClassification.from_path(None)

    assert gate.to_dict() == {
        "target_family": "swing_setup",
        "target_kind": "gate",
        "target_parameter": "min_foreign_flow_score",
    }
    assert unknown.to_dict() == {
        "target_family": "unknown",
        "target_kind": "unknown",
        "target_parameter": "unknown",
    }


def test_interpretation_wording_maps_machine_policy_to_user_meaning():
    assert tuning_config_diff_item_interpretation(
        "PROPOSED_VALUE_SELECTED",
        "DETERMINISTIC_VALUE_SELECTED",
    ) == "proposed guarded value"
    assert tuning_config_diff_item_interpretation(
        "CURRENT_VALUE_ONLY",
        "NON_NUMERIC_CURRENT_VALUE",
    ) == "read-only current value; non-numeric config"
    assert tuning_config_diff_rejection_interpretation(
        "DOCUMENT_PATH_NOT_FOUND"
    ) == "not resolved; YAML path missing"


def test_rejection_policy_mapping_is_deterministic():
    assert (
        value_selection_policy_for_rejection("wildcard_path_not_resolved")
        == "WILDCARD_UNRESOLVED"
    )
    assert (
        value_selection_policy_for_rejection("config_file_not_found")
        == "CONFIG_FILE_NOT_FOUND"
    )
    assert (
        value_selection_policy_for_rejection("document_path_not_found")
        == "DOCUMENT_PATH_NOT_FOUND"
    )
    assert (
        value_selection_policy_for_rejection("unexpected")
        == "CONFIG_VALUE_NOT_RESOLVED"
    )


def test_review_checklist_reflects_proposed_current_only_and_rejected_rows():
    checklist = build_tuning_config_diff_review_checklist(
        (
            _DiffItem(
                proposed_value=71,
                value_selection_policy="DETERMINISTIC_VALUE_SELECTED",
            ),
            _DiffItem(
                proposed_value=None,
                value_selection_policy="INSUFFICIENT_EVIDENCE",
            ),
        ),
        (_RejectedItem(),),
    )

    assert "Review every proposed value before editing YAML manually." in checklist
    assert "Inspect current-only rows before treating them as tunable." in checklist
    assert "Resolve rejected rows before expecting a complete tuning diff." in checklist
    assert checklist[-1] == (
        "Do not apply automatically; edit YAML manually only after review."
    )


def test_config_diff_summary_counts_rows_policies_and_evidence_dimensions():
    summary = build_tuning_config_diff_summary(
        (
            _DiffItem(
                proposed_value=71,
                value_selection_policy="DETERMINISTIC_VALUE_SELECTED",
                evidence_dimension="signal_strength",
                evidence_dimensions=("signal_strength", "trade_setup_action"),
            ),
            _DiffItem(
                proposed_value=None,
                value_selection_policy="INSUFFICIENT_EVIDENCE",
                evidence_dimension="setup_gate",
            ),
        ),
        (_RejectedItem(),),
    )

    assert summary["resolved_count"] == 2
    assert summary["proposed_count"] == 1
    assert summary["current_only_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["value_policy_counts"] == {
        "DETERMINISTIC_VALUE_SELECTED": 1,
        "INSUFFICIENT_EVIDENCE": 1,
    }
    assert summary["evidence_dimension_counts"] == {
        "setup_gate": 1,
        "signal_strength": 1,
        "trade_setup_action": 1,
    }


def test_suggest_tuning_value_selects_guarded_numeric_value():
    candidate = _Candidate(
        dimension="signal_strength",
        evidence_strength="HIGH",
        evidence_buckets=(
            "STRONG | n=20 | avg=-2.00%",
            "WEAK | n=20 | avg=+4.00%",
        ),
    )
    resolution = TuningConfigValueResolution(
        target_path=_path(
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
        ),
        resolved=True,
        current_value=70,
    )

    suggestion = suggest_tuning_value(candidate, resolution)

    assert suggestion.proposed_value == 71
    assert suggestion.status == "PROPOSED_VALUE_SELECTED"
    assert suggestion.value_selection_policy == "DETERMINISTIC_VALUE_SELECTED"


def test_suggest_tuning_value_keeps_non_numeric_and_low_evidence_read_only():
    non_numeric = suggest_tuning_value(
        _Candidate(
            dimension="setup_gate",
            evidence_strength="HIGH",
            evidence_buckets=("required_trend:PASS | n=20 | avg=+2.00%",),
        ),
        TuningConfigValueResolution(
            target_path=_path(
                "config/swing_setups.yaml:setups.foreign-bounce.gates.required_trend"
            ),
            resolved=True,
            current_value="SIDE",
        ),
    )
    low_evidence = suggest_tuning_value(
        _Candidate(
            dimension="signal_strength",
            evidence_strength="MEDIUM",
            evidence_buckets=(
                "STRONG | n=15 | avg=-2.00%",
                "WEAK | n=15 | avg=+2.00%",
            ),
        ),
        TuningConfigValueResolution(
            target_path=_path(
                "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
            ),
            resolved=True,
            current_value=70,
        ),
    )

    assert non_numeric.proposed_value is None
    assert non_numeric.value_selection_policy == "NON_NUMERIC_CURRENT_VALUE"
    assert low_evidence.proposed_value is None
    assert low_evidence.value_selection_policy == "INSUFFICIENT_EVIDENCE"
