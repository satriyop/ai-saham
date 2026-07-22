"""Adversarial tests for typed semantic-contract domain contracts."""

from __future__ import annotations

from copy import deepcopy

import pytest

from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY,
    ACCUMULATION_DISCOVERY_CONTRACT,
    EVIDENCE_CONTRACT_VERSION,
    SEMANTIC_ENGINE_VERSION,
    SemanticContractDefinition,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_COMMON_PATHS = (
    "signal_engine.alpha_trigger.default_horizon",
    "signal_engine.classification.moderate_min_score",
    "signal_engine.classification.strong_min_score",
)

_VALID_FAMILY_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "accumulation",
        (
            "swing_setups.setups.foreign-bounce.enabled",
            "swing_setups.setups.foreign-bounce.entry_authority",
        ),
    ),
)

_VALID_HORIZON_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "SWING_10D",
        (
            "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D",
        ),
    ),
    (
        "TACTICAL_3D",
        (
            "signal_engine.alpha_trigger.horizon_alpha_weights.TACTICAL_3D",
        ),
    ),
)

_VALID_POLICY_VERSIONS: tuple[tuple[str, str], ...] = (
    ("TACTICAL_3D", "tactical_3d_v1"),
    ("SWING_10D", "swing_10d_v1"),
)

_AUTHORITY_NAMES = ("company_quality_context", "setup_quality")


def _valid(**overrides) -> SemanticContractDefinition:
    kwargs = dict(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        evidence_contract_version=EVIDENCE_CONTRACT_VERSION,
        semantic_engine_version=SEMANTIC_ENGINE_VERSION,
        observation_schema_version=CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        label_schema_version=SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
        execution_label_policy_versions=_VALID_POLICY_VERSIONS,
        common_material_config_paths=_VALID_COMMON_PATHS,
        material_config_paths_by_setup_family=_VALID_FAMILY_PATHS,
        material_config_paths_by_evaluation_horizon=_VALID_HORIZON_PATHS,
        authority_registration_names=_AUTHORITY_NAMES,
    )
    kwargs.update(overrides)
    return SemanticContractDefinition(**kwargs)


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------


def test_valid_contract():
    c = _valid()
    assert c.observation_contract == ACCUMULATION_DISCOVERY_CONTRACT
    assert c.evidence_contract_version == EVIDENCE_CONTRACT_VERSION
    assert c.semantic_engine_version == SEMANTIC_ENGINE_VERSION


def test_known_instance_exists():
    assert ACCUMULATION_DISCOVERY.observation_contract == ACCUMULATION_DISCOVERY_CONTRACT
    assert ACCUMULATION_DISCOVERY.evidence_contract_version == "1.4"
    assert ACCUMULATION_DISCOVERY.semantic_engine_version == "1.3"
    assert ACCUMULATION_DISCOVERY.observation_schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    assert ACCUMULATION_DISCOVERY.label_schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION
    assert len(ACCUMULATION_DISCOVERY.common_material_config_paths) > 0
    assert len(ACCUMULATION_DISCOVERY.material_config_paths_by_setup_family) == 5
    assert len(ACCUMULATION_DISCOVERY.material_config_paths_by_evaluation_horizon) == 3


def test_known_instance_normalization_paths_declared():
    assert len(ACCUMULATION_DISCOVERY.unordered_upper_string_config_paths) == 7
    assert len(ACCUMULATION_DISCOVERY.unordered_lower_string_config_paths) == 1
    assert (
        "swing_setups.setup_phase.volume_trigger.trusted_benchmark_volume_sources"
        in ACCUMULATION_DISCOVERY.unordered_lower_string_config_paths
    )
    all_normalization_paths = (
        ACCUMULATION_DISCOVERY.unordered_upper_string_config_paths
        + ACCUMULATION_DISCOVERY.unordered_lower_string_config_paths
    )
    for family in ("accumulation", "breakout", "pullback"):
        required_sequence_path = (
            f"swing_setups.setup_phase.requirements.{family}.required_sequence"
        )
        assert required_sequence_path not in all_normalization_paths, (
            "required_sequence order is semantic and must not be normalized"
        )


# ---------------------------------------------------------------------------
# material_paths_for
# ---------------------------------------------------------------------------


def test_material_paths_for_none_family_uses_common_and_horizon():
    c = _valid()
    paths = c.material_paths_for(setup_family=None, evaluation_horizon="SWING_10D")
    assert set(_VALID_COMMON_PATHS) <= set(paths)
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D" in paths
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.TACTICAL_3D" not in paths


def test_material_paths_for_accumulation_includes_common_horizon_and_family():
    c = _valid()
    paths = c.material_paths_for(setup_family="accumulation", evaluation_horizon="SWING_10D")
    assert "swing_setups.setups.foreign-bounce.enabled" in paths
    assert "signal_engine.classification.moderate_min_score" in paths
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D" in paths


def test_material_paths_for_unknown_family_raises():
    c = _valid()
    with pytest.raises(ValueError, match="unknown setup_family"):
        c.material_paths_for(setup_family="nonexistent", evaluation_horizon="SWING_10D")


def test_material_paths_for_unknown_horizon_raises():
    c = _valid()
    with pytest.raises(ValueError, match="unknown evaluation_horizon"):
        c.material_paths_for(setup_family=None, evaluation_horizon="FAKE_1D")


def test_material_paths_for_only_selected_horizon_present():
    c = _valid()
    swing_paths = c.material_paths_for(setup_family=None, evaluation_horizon="SWING_10D")
    tactical_paths = c.material_paths_for(setup_family=None, evaluation_horizon="TACTICAL_3D")
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D" in swing_paths
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.TACTICAL_3D" not in swing_paths
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.TACTICAL_3D" in tactical_paths
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D" not in tactical_paths


def test_material_paths_for_includes_selected_family():
    c = _valid()
    paths = c.material_paths_for(setup_family="accumulation", evaluation_horizon="SWING_10D")
    assert "swing_setups.setups.foreign-bounce.enabled" in paths
    assert "swing_setups.setups.foreign-bounce.entry_authority" in paths


# ---------------------------------------------------------------------------
# Label policy version lookup
# ---------------------------------------------------------------------------


def test_label_policy_version_found():
    c = _valid()
    assert c.label_policy_version("TACTICAL_3D") == "tactical_3d_v1"


def test_label_policy_version_unknown_raises():
    c = _valid()
    with pytest.raises(ValueError, match="unknown horizon"):
        c.label_policy_version("FAKE_1D")


# ---------------------------------------------------------------------------
# Validation — observation_contract
# ---------------------------------------------------------------------------


def test_empty_observation_contract_raises():
    with pytest.raises(ValueError, match="observation_contract"):
        _valid(observation_contract="")


def test_whitespace_observation_contract_raises():
    with pytest.raises(ValueError, match="observation_contract"):
        _valid(observation_contract="  ")


def test_whitespace_surrounding_observation_contract_raises():
    with pytest.raises(ValueError, match="observation_contract"):
        _valid(observation_contract=" test ")


# ---------------------------------------------------------------------------
# Validation — evidence_contract_version
# ---------------------------------------------------------------------------


def test_empty_evidence_contract_version_raises():
    with pytest.raises(ValueError, match="evidence_contract_version"):
        _valid(evidence_contract_version="")


# ---------------------------------------------------------------------------
# Validation — semantic_engine_version
# ---------------------------------------------------------------------------


def test_empty_semantic_engine_version_raises():
    with pytest.raises(ValueError, match="semantic_engine_version"):
        _valid(semantic_engine_version="")


# ---------------------------------------------------------------------------
# Validation — schema versions
# ---------------------------------------------------------------------------


def test_zero_observation_schema_version_raises():
    with pytest.raises(ValueError, match="observation_schema_version"):
        _valid(observation_schema_version=0)


def test_negative_observation_schema_version_raises():
    with pytest.raises(ValueError, match="observation_schema_version"):
        _valid(observation_schema_version=-1)


def test_observation_schema_not_int_raises():
    with pytest.raises(ValueError, match="observation_schema_version"):
        _valid(observation_schema_version="3")


def test_zero_label_schema_version_raises():
    with pytest.raises(ValueError, match="label_schema_version"):
        _valid(label_schema_version=0)


def test_label_schema_not_int_raises():
    with pytest.raises(ValueError, match="label_schema_version"):
        _valid(label_schema_version=False)


# ---------------------------------------------------------------------------
# Validation — execution_label_policy_versions
# ---------------------------------------------------------------------------


def test_empty_policy_versions_raises():
    with pytest.raises(ValueError, match="execution_label_policy_versions"):
        _valid(execution_label_policy_versions=())


def test_duplicate_horizon_raises():
    with pytest.raises(ValueError, match="duplicate horizon"):
        _valid(execution_label_policy_versions=(
            ("TACTICAL_3D", "v1"),
            ("TACTICAL_3D", "v2"),
        ))


def test_empty_horizon_raises():
    with pytest.raises(ValueError, match="horizon"):
        _valid(execution_label_policy_versions=(
            ("", "v1"),
        ))


def test_empty_version_raises():
    with pytest.raises(ValueError, match="version"):
        _valid(execution_label_policy_versions=(
            ("TACTICAL_3D", ""),
        ))


# ---------------------------------------------------------------------------
# Validation — common_material_config_paths
# ---------------------------------------------------------------------------


def test_empty_common_paths_raises():
    with pytest.raises(ValueError, match="common_material_config_paths"):
        _valid(common_material_config_paths=())


def test_unsorted_common_paths_raises():
    with pytest.raises(ValueError, match="paths must be sorted"):
        _valid(common_material_config_paths=(
            "z.path",
            "a.path",
        ))


def test_duplicate_common_path_raises():
    with pytest.raises(ValueError, match="duplicate"):
        _valid(common_material_config_paths=(
            "a.path.one",
            "a.path.one",
        ))


def test_invalid_dotted_path_segments_raises():
    with pytest.raises(ValueError, match="invalid dotted path"):
        _valid(common_material_config_paths=(
            "no_dots",
        ))


def test_path_starting_with_dot_raises():
    with pytest.raises(ValueError, match="invalid dotted path"):
        _valid(common_material_config_paths=(
            ".starts.with.dot",
        ))


def test_common_paths_missing_horizon_selector_raises():
    """The evaluation-horizon selector path must always be common material,
    or a changed default_horizon could silently repoint which horizon-scoped
    paths are hashed without changing identity."""
    with pytest.raises(ValueError, match="evaluation-horizon selector"):
        _valid(common_material_config_paths=(
            "signal_engine.classification.moderate_min_score",
            "signal_engine.classification.strong_min_score",
        ))


# ---------------------------------------------------------------------------
# Validation — material_config_paths_by_setup_family
# ---------------------------------------------------------------------------


def test_duplicate_family_name_raises():
    fam = deepcopy(_VALID_FAMILY_PATHS)
    fam_dict = dict(fam)
    duo = (
        ("accumulation", fam_dict["accumulation"]),
        ("accumulation", fam_dict["accumulation"]),
    )
    with pytest.raises(ValueError, match="duplicate family"):
        _valid(material_config_paths_by_setup_family=duo)


def test_invalid_family_name_raises():
    with pytest.raises(ValueError, match="invalid family name"):
        _valid(material_config_paths_by_setup_family=(
            ("Invalid-Family!", ("a.path.one",)),
        ))


def test_unsorted_family_paths_raises():
    with pytest.raises(ValueError, match="paths must be sorted"):
        _valid(material_config_paths_by_setup_family=(
            ("accumulation", ("z.path", "a.path")),
        ))


# ---------------------------------------------------------------------------
# Validation — material_config_paths_by_evaluation_horizon
# ---------------------------------------------------------------------------


def test_empty_horizon_groups_raises():
    with pytest.raises(ValueError, match="material_config_paths_by_evaluation_horizon"):
        _valid(material_config_paths_by_evaluation_horizon=())


def test_duplicate_horizon_group_name_raises():
    with pytest.raises(ValueError, match="duplicate horizon"):
        _valid(material_config_paths_by_evaluation_horizon=(
            ("SWING_10D", ("a.path.one",)),
            ("SWING_10D", ("a.path.two",)),
        ))


def test_unknown_evaluation_horizon_group_name_rejected_by_lookup():
    c = _valid()
    with pytest.raises(ValueError, match="unknown evaluation_horizon"):
        c.material_paths_for(setup_family=None, evaluation_horizon="UNKNOWN_HORIZON")


def test_unsorted_horizon_groups_raises():
    with pytest.raises(ValueError, match="horizon groups must be sorted"):
        _valid(material_config_paths_by_evaluation_horizon=(
            ("TACTICAL_3D", ("a.path.one",)),
            ("SWING_10D", ("a.path.two",)),
        ))


def test_unsorted_horizon_paths_raises():
    with pytest.raises(ValueError, match="paths must be sorted"):
        _valid(material_config_paths_by_evaluation_horizon=(
            ("SWING_10D", ("z.path", "a.path")),
        ))


def test_duplicate_horizon_paths_raises():
    with pytest.raises(ValueError, match="duplicate path"):
        _valid(material_config_paths_by_evaluation_horizon=(
            ("SWING_10D", ("a.path.one", "a.path.one")),
        ))


def test_empty_horizon_paths_raises():
    with pytest.raises(ValueError, match="non-empty tuple"):
        _valid(material_config_paths_by_evaluation_horizon=(
            ("SWING_10D", ()),
        ))


# ---------------------------------------------------------------------------
# Validation — authority_registration_names
# ---------------------------------------------------------------------------


def test_empty_authority_names_raises():
    with pytest.raises(ValueError, match="authority_registration_names"):
        _valid(authority_registration_names=())


def test_unsorted_authority_names_raises():
    with pytest.raises(ValueError, match="must be sorted"):
        _valid(authority_registration_names=("z", "a"))


def test_duplicate_authority_name_raises():
    with pytest.raises(ValueError, match="duplicate"):
        _valid(authority_registration_names=("a", "a"))


# ---------------------------------------------------------------------------
# Validation — unordered normalization metadata
# ---------------------------------------------------------------------------


def test_normalization_paths_default_to_empty():
    c = _valid()
    assert c.unordered_upper_string_config_paths == ()
    assert c.unordered_lower_string_config_paths == ()


def test_valid_contract_with_normalization_paths():
    c = _valid(
        unordered_upper_string_config_paths=(
            "signal_engine.classification.moderate_min_score",
        ),
        unordered_lower_string_config_paths=(
            "swing_setups.setups.foreign-bounce.enabled",
        ),
    )
    assert c.unordered_upper_string_config_paths == (
        "signal_engine.classification.moderate_min_score",
    )
    assert c.unordered_lower_string_config_paths == (
        "swing_setups.setups.foreign-bounce.enabled",
    )


def test_unordered_upper_paths_must_be_sorted():
    with pytest.raises(ValueError, match="paths must be sorted"):
        _valid(unordered_upper_string_config_paths=(
            "signal_engine.classification.strong_min_score",
            "signal_engine.classification.moderate_min_score",
        ))


def test_unordered_lower_paths_must_be_sorted():
    with pytest.raises(ValueError, match="paths must be sorted"):
        _valid(unordered_lower_string_config_paths=(
            "signal_engine.classification.strong_min_score",
            "signal_engine.classification.moderate_min_score",
        ))


def test_unordered_upper_paths_duplicate_raises():
    with pytest.raises(ValueError, match="duplicate path"):
        _valid(unordered_upper_string_config_paths=(
            "signal_engine.classification.moderate_min_score",
            "signal_engine.classification.moderate_min_score",
        ))


def test_unordered_lower_paths_invalid_dotted_path_raises():
    with pytest.raises(ValueError, match="invalid dotted path"):
        _valid(unordered_lower_string_config_paths=("no_dots",))


def test_unordered_upper_and_lower_paths_must_not_overlap():
    with pytest.raises(ValueError, match="must not overlap"):
        _valid(
            unordered_upper_string_config_paths=(
                "signal_engine.classification.moderate_min_score",
            ),
            unordered_lower_string_config_paths=(
                "signal_engine.classification.moderate_min_score",
            ),
        )


def test_unordered_upper_path_must_be_declared_material():
    with pytest.raises(ValueError, match="not declared in common, family, or horizon"):
        _valid(unordered_upper_string_config_paths=("not.a.material.path",))


def test_unordered_lower_path_must_be_declared_material():
    with pytest.raises(ValueError, match="not declared in common, family, or horizon"):
        _valid(unordered_lower_string_config_paths=("not.a.material.path",))


def test_unordered_upper_path_declared_only_in_family_is_accepted():
    c = _valid(unordered_upper_string_config_paths=(
        "swing_setups.setups.foreign-bounce.entry_authority",
    ))
    assert c.unordered_upper_string_config_paths == (
        "swing_setups.setups.foreign-bounce.entry_authority",
    )


def test_unordered_upper_path_declared_only_in_horizon_is_accepted():
    c = _valid(unordered_upper_string_config_paths=(
        "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D",
    ))
    assert c.unordered_upper_string_config_paths == (
        "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D",
    )


# ---------------------------------------------------------------------------
# Validation — unordered_integer_config_paths / commodity_component_config_paths
# ---------------------------------------------------------------------------


def test_integer_and_commodity_normalization_paths_default_to_empty():
    c = _valid()
    assert c.unordered_integer_config_paths == ()
    assert c.commodity_component_config_paths == ()


def test_valid_contract_with_integer_and_commodity_normalization_paths():
    c = _valid(
        unordered_integer_config_paths=(
            "signal_engine.classification.moderate_min_score",
        ),
        commodity_component_config_paths=(
            "signal_engine.classification.strong_min_score",
        ),
    )
    assert c.unordered_integer_config_paths == (
        "signal_engine.classification.moderate_min_score",
    )
    assert c.commodity_component_config_paths == (
        "signal_engine.classification.strong_min_score",
    )


def test_unordered_integer_paths_must_be_sorted():
    with pytest.raises(ValueError, match="paths must be sorted"):
        _valid(unordered_integer_config_paths=(
            "signal_engine.classification.strong_min_score",
            "signal_engine.classification.moderate_min_score",
        ))


def test_commodity_component_paths_must_be_sorted():
    with pytest.raises(ValueError, match="paths must be sorted"):
        _valid(commodity_component_config_paths=(
            "signal_engine.classification.strong_min_score",
            "signal_engine.classification.moderate_min_score",
        ))


def test_unordered_integer_paths_duplicate_raises():
    with pytest.raises(ValueError, match="duplicate path"):
        _valid(unordered_integer_config_paths=(
            "signal_engine.classification.moderate_min_score",
            "signal_engine.classification.moderate_min_score",
        ))


def test_unordered_integer_path_invalid_dotted_path_raises():
    with pytest.raises(ValueError, match="invalid dotted path"):
        _valid(unordered_integer_config_paths=("no_dots",))


def test_unordered_integer_path_must_be_declared_material():
    with pytest.raises(ValueError, match="not declared in common, family, or horizon"):
        _valid(unordered_integer_config_paths=("not.a.material.path",))


def test_commodity_component_path_must_be_declared_material():
    with pytest.raises(ValueError, match="not declared in common, family, or horizon"):
        _valid(commodity_component_config_paths=("not.a.material.path",))


def test_unordered_integer_path_overlapping_upper_string_path_raises():
    with pytest.raises(ValueError, match="must not overlap"):
        _valid(
            unordered_upper_string_config_paths=(
                "signal_engine.classification.moderate_min_score",
            ),
            unordered_integer_config_paths=(
                "signal_engine.classification.moderate_min_score",
            ),
        )


def test_commodity_component_path_overlapping_lower_string_path_raises():
    with pytest.raises(ValueError, match="must not overlap"):
        _valid(
            unordered_lower_string_config_paths=(
                "signal_engine.classification.moderate_min_score",
            ),
            commodity_component_config_paths=(
                "signal_engine.classification.moderate_min_score",
            ),
        )


def test_unordered_integer_path_overlapping_commodity_path_raises():
    with pytest.raises(ValueError, match="must not overlap"):
        _valid(
            unordered_integer_config_paths=(
                "signal_engine.classification.moderate_min_score",
            ),
            commodity_component_config_paths=(
                "signal_engine.classification.moderate_min_score",
            ),
        )


def test_known_instance_integer_and_commodity_paths_declared():
    assert ACCUMULATION_DISCOVERY.unordered_integer_config_paths == (
        "institutional_accumulation.windows.broker_consistency_days",
        "institutional_accumulation.windows.cnfb_bearish_distribution",
        "institutional_accumulation.windows.cnfb_bullish_accumulation",
    )
    assert ACCUMULATION_DISCOVERY.commodity_component_config_paths == (
        "market_context_engine.factors.commodity_composite.components",
    )
    # Unordered integer config paths are modeled as unordered multisets.
    # Reordering is non-semantic, but duplicate multiplicity remains semantic.
    # Scalar day counts and required_sequence must never be normalized.
    all_normalization_paths = (
        ACCUMULATION_DISCOVERY.unordered_upper_string_config_paths
        + ACCUMULATION_DISCOVERY.unordered_lower_string_config_paths
        + ACCUMULATION_DISCOVERY.unordered_integer_config_paths
        + ACCUMULATION_DISCOVERY.commodity_component_config_paths
    )
    for forbidden in (
        "institutional_accumulation.windows.foreign_vwap_days",
        "institutional_accumulation.windows.domestic_vwap_days",
        "institutional_accumulation.windows.counterparty_window_days",
    ):
        assert forbidden not in all_normalization_paths


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_immutable_frozen_dataclass():
    c = _valid()
    with pytest.raises(AttributeError):
        c.observation_contract = "other"  # type: ignore[misc]
