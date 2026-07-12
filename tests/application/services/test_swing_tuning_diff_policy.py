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


def _idr_candidate() -> _Candidate:
    # Risk engine gate paths are driven by candidate_risk_status evidence.
    # BLOCKED avg > OPEN avg means the gate blocks too many good candidates → loosen.
    return _Candidate(
        dimension="candidate_risk_status",
        evidence_strength="HIGH",
        evidence_buckets=("BLOCKED | n=50 | avg=+2.00%", "OPEN | n=150 | avg=-0.50%"),
    )


def test_market_cap_floor_idr_uses_100b_step_not_integer_plus_one():
    resolution = TuningConfigValueResolution(
        target_path=_path(
            "config/risk_engine.yaml:risk_engine.gates.liquidity.market_cap_floor_idr"
        ),
        resolved=True,
        current_value=1_000_000_000_000,
    )

    suggestion = suggest_tuning_value(_idr_candidate(), resolution)

    assert suggestion.status == "PROPOSED_VALUE_SELECTED"
    assert suggestion.proposed_value != 999_999_999_999, "must not produce +/-1 IDR noise"
    assert suggestion.proposed_value % int(1e11) == 0, "must be quantized to 100B step"


def test_median_tx_floor_idr_uses_1b_step_not_integer_plus_one():
    resolution = TuningConfigValueResolution(
        target_path=_path(
            "config/risk_engine.yaml:risk_engine.gates.liquidity.median_tx_floor_idr"
        ),
        resolved=True,
        current_value=5_000_000_000,
    )

    suggestion = suggest_tuning_value(_idr_candidate(), resolution)

    assert suggestion.status == "PROPOSED_VALUE_SELECTED"
    assert suggestion.proposed_value != 4_999_999_999, "must not produce +/-1 IDR noise"
    assert suggestion.proposed_value % int(1e9) == 0, "must be quantized to 1B step"


def test_target_classification_kinds():
    # Weight
    weight_path = _path("config/swing_setups.yaml:setups.foreign-bounce.weights.setup_weight")
    assert TuningTargetClassification.from_path(weight_path).target_kind == "weight"

    # Exit Rule
    exit_path = _path("config/swing_setups.yaml:setups.foreign-bounce.exit.take_profit_pct")
    assert TuningTargetClassification.from_path(exit_path).target_kind == "exit_rule"

    # Threshold
    threshold_path = _path("config/signal_engine.yaml:signal_engine.min_volume_threshold")
    assert TuningTargetClassification.from_path(threshold_path).target_kind == "threshold"


def test_suggest_tuning_value_non_numeric():
    candidate = _Candidate(
        dimension="signal_strength",
        evidence_strength="HIGH",
        evidence_buckets=(),
    )
    resolution = TuningConfigValueResolution(
        target_path=_path(
            "config/signal_engine.yaml:signal_engine.classification.enabled"
        ),
        resolved=True,
        current_value=True,
    )
    suggestion = suggest_tuning_value(candidate, resolution)
    assert suggestion.proposed_value is None
    assert suggestion.value_selection_policy == "NON_NUMERIC_CURRENT_VALUE"


def test_suggest_tuning_value_insufficient_evidence():
    candidate = _Candidate(
        dimension="signal_strength",
        evidence_strength="LOW",
        evidence_buckets=(),
    )
    resolution = TuningConfigValueResolution(
        target_path=_path(
            "config/signal_engine.yaml:signal_engine.classification.strong_min_score"
        ),
        resolved=True,
        current_value=70,
    )
    suggestion = suggest_tuning_value(candidate, resolution)
    assert suggestion.proposed_value is None
    assert suggestion.value_selection_policy == "INSUFFICIENT_EVIDENCE"


def test_suggest_tuning_value_no_deterministic_direction():
    candidate = _Candidate(
        dimension="signal_strength",
        evidence_strength="HIGH",
        evidence_buckets=(
            "STRONG | n=20 | avg=5.00%",
            "MODERATE | n=20 | avg=1.00%",
            "WEAK | n=20 | avg=2.00%",
        ),
    )
    resolution = TuningConfigValueResolution(
        target_path=_path("config/signal_engine.yaml:signal_engine.classification.strong_min_score"),
        resolved=True,
        current_value=70,
    )
    suggestion = suggest_tuning_value(candidate, resolution)
    assert suggestion.proposed_value is None
    assert suggestion.value_selection_policy == "NO_DETERMINISTIC_DIRECTION"


def test_suggest_tuning_value_no_unambiguous_direction():
    candidate = _Candidate(
        dimension="signal_strength",
        evidence_strength="HIGH",
        evidence_buckets=(
            "STRONG | n=20 | avg=2.00%",
            "WEAK | n=20 | avg=4.00%",
        ),
    )
    resolution = TuningConfigValueResolution(
        target_path=_path("config/swing_setups.yaml:setups.foreign-bounce.some_neutral_param"),
        resolved=True,
        current_value=70,
    )
    suggestion = suggest_tuning_value(candidate, resolution)
    assert suggestion.proposed_value is None
    assert suggestion.value_selection_policy == "NO_UNAMBIGUOUS_DIRECTION"


def test_exact_proposed_values_deterministic():
    candidate_tighten = _Candidate(
        dimension="signal_strength",
        evidence_strength="HIGH",
        evidence_buckets=(
            "STRONG | n=20 | avg=2.00%",
            "WEAK | n=20 | avg=4.00%",
        ),
    )
    res_int = TuningConfigValueResolution(
        target_path=_path("config/signal_engine.yaml:signal_engine.classification.strong_min_score"),
        resolved=True,
        current_value=70,
    )
    assert suggest_tuning_value(candidate_tighten, res_int).proposed_value == 71

    res_float = TuningConfigValueResolution(
        target_path=_path("config/signal_engine.yaml:signal_engine.classification.strong_min_score"),
        resolved=True,
        current_value=70.2,
    )
    assert suggest_tuning_value(candidate_tighten, res_float).proposed_value == 70.7


def test_weight_grid_snapping():
    candidate_tighten = _Candidate(
        dimension="signal_strength",
        evidence_strength="HIGH",
        evidence_buckets=(
            "STRONG | n=20 | avg=2.00%",
            "WEAK | n=20 | avg=4.00%",
        ),
    )
    resolution = TuningConfigValueResolution(
        target_path=_path("config/signal_engine.yaml:signal_engine.classification.enter_min_confidence"),
        resolved=True,
        current_value=0.72,
    )
    suggestion = suggest_tuning_value(candidate_tighten, resolution)
    assert suggestion.proposed_value == 0.75

    resolution2 = TuningConfigValueResolution(
        target_path=_path("config/signal_engine.yaml:signal_engine.classification.enter_min_confidence"),
        resolved=True,
        current_value=0.73,
    )
    suggestion2 = suggest_tuning_value(candidate_tighten, resolution2)
    assert suggestion2.proposed_value == 0.80


def test_custom_step_override_behavior():
    resolution = TuningConfigValueResolution(
        target_path=_path(
            "config/risk_engine.yaml:risk_engine.gates.liquidity.market_cap_floor_idr"
        ),
        resolved=True,
        current_value=1_040_000_000_000,
    )
    suggestion = suggest_tuning_value(_idr_candidate(), resolution)
    assert suggestion.proposed_value == 900_000_000_000


def test_priority_ordering():
    from src.application.services.swing_tuning_diff_policy import (
        tuning_diff_item_priority,
    )

    assert (
        tuning_diff_item_priority(
            _DiffItem(
                proposed_value=71,
                value_selection_policy="DETERMINISTIC_VALUE_SELECTED",
            )
        )
        == 100
    )
    assert (
        tuning_diff_item_priority(
            _DiffItem(
                proposed_value=None,
                value_selection_policy="DETERMINISTIC_VALUE_SELECTED",
            )
        )
        == 100
    )
    assert (
        tuning_diff_item_priority(
            _DiffItem(
                proposed_value=None,
                value_selection_policy="NO_DETERMINISTIC_DIRECTION",
            )
        )
        == 80
    )
    assert (
        tuning_diff_item_priority(
            _DiffItem(
                proposed_value=None,
                value_selection_policy="INSUFFICIENT_EVIDENCE",
            )
        )
        == 70
    )
    assert (
        tuning_diff_item_priority(
            _DiffItem(
                proposed_value=None,
                value_selection_policy="NO_UNAMBIGUOUS_DIRECTION",
            )
        )
        == 60
    )
    assert (
        tuning_diff_item_priority(
            _DiffItem(
                proposed_value=None,
                value_selection_policy="NON_NUMERIC_CURRENT_VALUE",
            )
        )
        == 50
    )
    assert (
        tuning_diff_item_priority(
            _DiffItem(
                proposed_value=None,
                value_selection_policy="UNKNOWN_POLICY",
            )
        )
        == 10
    )


def test_facade_compatibility_imports_work():
    # Facade imports
    # Directly imported from new modules
    from src.application.services.swing_tuning_diff_interpretation import (
        tuning_config_diff_item_interpretation,
        tuning_config_diff_rejection_interpretation,
        tuning_diff_item_priority,
    )
    from src.application.services.swing_tuning_diff_policy import (
        TuningTargetClassification as FacadeTuningTargetClassification,
    )
    from src.application.services.swing_tuning_diff_policy import (
        TuningValueSuggestion as FacadeTuningValueSuggestion,
    )
    from src.application.services.swing_tuning_diff_policy import (
        build_tuning_config_diff_review_checklist as facade_checklist,
    )
    from src.application.services.swing_tuning_diff_policy import (
        build_tuning_config_diff_summary as facade_summary,
    )
    from src.application.services.swing_tuning_diff_policy import (
        suggest_tuning_value as facade_suggest,
    )
    from src.application.services.swing_tuning_diff_policy import (
        tuning_config_diff_item_interpretation as facade_item_interp,
    )
    from src.application.services.swing_tuning_diff_policy import (
        tuning_config_diff_rejection_interpretation as facade_rej_interp,
    )
    from src.application.services.swing_tuning_diff_policy import (
        tuning_diff_item_priority as facade_priority,
    )
    from src.application.services.swing_tuning_diff_policy import (
        value_selection_policy_for_rejection as facade_rejection_policy,
    )
    from src.application.services.swing_tuning_diff_summary_policy import (
        build_tuning_config_diff_review_checklist,
        build_tuning_config_diff_summary,
    )
    from src.application.services.swing_tuning_target_classification import (
        TuningTargetClassification,
    )
    from src.application.services.swing_tuning_value_suggestion_policy import (
        TuningValueSuggestion,
        suggest_tuning_value,
        value_selection_policy_for_rejection,
    )

    # Verify identity using 'is'
    assert FacadeTuningTargetClassification is TuningTargetClassification
    assert FacadeTuningValueSuggestion is TuningValueSuggestion
    assert facade_checklist is build_tuning_config_diff_review_checklist
    assert facade_summary is build_tuning_config_diff_summary
    assert facade_suggest is suggest_tuning_value
    assert facade_item_interp is tuning_config_diff_item_interpretation
    assert facade_rej_interp is tuning_config_diff_rejection_interpretation
    assert facade_priority is tuning_diff_item_priority
    assert facade_rejection_policy is value_selection_policy_for_rejection
