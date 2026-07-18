"""Adversarial tests for SignalSemanticContractRegistry.

Tests use locally defined fixtures built from public domain types, and a
test-only loader that reads the real owned YAML config documents.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Mapping

import pytest
import yaml

from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityDimensions,
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY,
    ACCUMULATION_DISCOVERY_CONTRACT,
    EVIDENCE_CONTRACT_VERSION,
    SEMANTIC_ENGINE_VERSION,
    SemanticContractDefinition,
)
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon
from src.domain.value_objects.alpha_trigger_score import (
    EvidenceAuthorityStatus,
    EvidenceRegistration,
)
from src.application.services.signal_semantic_contract_registry import (
    SignalSemanticContractRegistry,
)
from src.application.services.signal_artifact_identity_resolver import (
    SignalArtifactIdentityResolver,
)
from src.application.services.engine_bootstrap.signal_scoring_config_resolver import (
    resolve_signal_engine_config,
)
from src.application.services.institutional_flow_config import (
    InstitutionalAccumulationConfig,
)
from src.infrastructure.config.market_context_config import load_market_context_config


# ---------------------------------------------------------------------------
# Small independent synthetic fixtures — generic hashing mechanics only.
# Do not make these depend on repository YAML.
# ---------------------------------------------------------------------------

_SMALL_COMMON_PATHS = (
    "signal_engine.alpha_trigger.default_horizon",
    "signal_engine.classification.moderate_min_score",
    "signal_engine.classification.strong_min_score",
)

_SMALL_FAMILY_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "accumulation",
        (
            "swing_setups.setups.foreign-bounce.enabled",
            "swing_setups.setups.foreign-bounce.gates.min_foreign_flow_score",
        ),
    ),
    (
        "breakout",
        (
            "swing_setups.setups.coiled-spring.enabled",
            "swing_setups.setups.coiled-spring.gates.max_bb_width_pctile",
        ),
    ),
)

_SMALL_HORIZON_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "ACCUM_20D",
        ("signal_engine.alpha_trigger.horizon_alpha_weights.ACCUM_20D",),
    ),
    (
        "SWING_10D",
        ("signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D",),
    ),
    (
        "TACTICAL_3D",
        ("signal_engine.alpha_trigger.horizon_alpha_weights.TACTICAL_3D",),
    ),
)

_SMALL_POLICY_VERSIONS: tuple[tuple[str, str], ...] = (
    ("TACTICAL_3D", "tactical_3d_v1"),
    ("SWING_10D", "swing_10d_v1"),
    ("ACCUM_20D", "accum_20d_v1"),
)

_AUTHORITY_NAMES = (
    "company_quality_context",
    "institutional_flow",
    "market_context",
    "setup_quality",
)


@pytest.fixture
def definition() -> SemanticContractDefinition:
    return SemanticContractDefinition(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        evidence_contract_version=EVIDENCE_CONTRACT_VERSION,
        semantic_engine_version=SEMANTIC_ENGINE_VERSION,
        observation_schema_version=CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        label_schema_version=SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
        execution_label_policy_versions=_SMALL_POLICY_VERSIONS,
        common_material_config_paths=_SMALL_COMMON_PATHS,
        material_config_paths_by_setup_family=_SMALL_FAMILY_PATHS,
        material_config_paths_by_evaluation_horizon=_SMALL_HORIZON_PATHS,
        authority_registration_names=_AUTHORITY_NAMES,
    )


@pytest.fixture
def registry(definition: SemanticContractDefinition) -> SignalSemanticContractRegistry:
    return SignalSemanticContractRegistry(definition)


@pytest.fixture
def material_values() -> dict[str, object]:
    return {
        "signal_engine.classification.moderate_min_score": 45,
        "signal_engine.classification.strong_min_score": 70,
        "signal_engine.alpha_trigger.default_horizon": "SWING_10D",
        "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D": 0.40,
    }


@pytest.fixture
def material_values_with_family(material_values: dict[str, object]) -> dict[str, object]:
    out = dict(material_values)
    out["swing_setups.setups.foreign-bounce.enabled"] = True
    out["swing_setups.setups.foreign-bounce.gates.min_foreign_flow_score"] = 58.3
    return out


@pytest.fixture
def authority_regs() -> dict[str, EvidenceRegistration]:
    return {
        "company_quality_context": EvidenceRegistration(
            evidence_name="company_quality_context",
            status=EvidenceAuthorityStatus.DIAGNOSTIC,
            low_weight_cap=0.10,
        ),
        "institutional_flow": EvidenceRegistration(
            evidence_name="institutional_flow",
            status=EvidenceAuthorityStatus.PRODUCTION,
            low_weight_cap=0.10,
        ),
        "market_context": EvidenceRegistration(
            evidence_name="market_context",
            status=EvidenceAuthorityStatus.DIAGNOSTIC,
            low_weight_cap=0.10,
        ),
        "setup_quality": EvidenceRegistration(
            evidence_name="setup_quality",
            status=EvidenceAuthorityStatus.PRODUCTION,
            low_weight_cap=0.10,
        ),
    }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_constructor_accepts_definition(registry: SignalSemanticContractRegistry):
    assert registry.definition.observation_contract == ACCUMULATION_DISCOVERY_CONTRACT


def test_constructor_rejects_non_definition():
    with pytest.raises(TypeError, match="definition"):
        SignalSemanticContractRegistry("not a definition")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Identical inputs produce identical hashes
# ---------------------------------------------------------------------------


def test_identical_observation_inputs_produce_identical_dimensions(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    a = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    b = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    assert a.material_config_hash == b.material_config_hash
    assert a.authority_registrations_hash == b.authority_registrations_hash
    assert a == b


def test_identical_label_inputs_produce_identical_dimensions(
    registry: SignalSemanticContractRegistry,
    material_values_with_family: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    a = registry.resolve_label(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family="accumulation",
        strategy_name=None,
        horizon=SignalLabelHorizon.SWING_10D,
        material_config_values=material_values_with_family,
        authority_registrations=authority_regs,
    )
    b = registry.resolve_label(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family="accumulation",
        strategy_name=None,
        horizon=SignalLabelHorizon.SWING_10D,
        material_config_values=material_values_with_family,
        authority_registrations=authority_regs,
    )
    assert a == b


# ---------------------------------------------------------------------------
# Input mapping order independence
# ---------------------------------------------------------------------------


def test_material_config_order_independence(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    reordered = dict(reversed(list(material_values.items())))
    a = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    b = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=reordered,
        authority_registrations=authority_regs,
    )
    assert a.material_config_hash == b.material_config_hash


def test_authority_registration_order_independence(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    reordered = {
        "setup_quality": authority_regs["setup_quality"],
        "market_context": authority_regs["market_context"],
        "institutional_flow": authority_regs["institutional_flow"],
        "company_quality_context": authority_regs["company_quality_context"],
    }
    a = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    b = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=reordered,
    )
    assert a.authority_registrations_hash == b.authority_registrations_hash


# ---------------------------------------------------------------------------
# Every declared material path individually changes hash
# ---------------------------------------------------------------------------


def test_each_common_path_changes_material_hash_individually(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    baseline = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    for path in _SMALL_COMMON_PATHS:
        if path == "signal_engine.alpha_trigger.default_horizon":
            continue
        altered = dict(material_values)
        val = altered[path]
        if isinstance(val, int):
            altered[path] = val + 1
        elif isinstance(val, float):
            altered[path] = val + 1.0
        else:
            altered[path] = f"changed-{val}"
        result = registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=altered,
            authority_registrations=authority_regs,
        )
        assert result.material_config_hash != baseline.material_config_hash, (
            f"path {path} did not change material_config_hash"
        )


def test_each_family_path_changes_hash(
    registry: SignalSemanticContractRegistry,
    material_values_with_family: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    baseline = registry.resolve_label(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family="accumulation",
        strategy_name=None,
        horizon=SignalLabelHorizon.SWING_10D,
        material_config_values=material_values_with_family,
        authority_registrations=authority_regs,
    )
    for path in _SMALL_FAMILY_PATHS[0][1]:
        altered = dict(material_values_with_family)
        val = altered[path]
        if isinstance(val, bool):
            altered[path] = not val
        elif isinstance(val, (int, float)):
            altered[path] = val + 1
        else:
            altered[path] = f"changed-{val}"
        result = registry.resolve_label(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family="accumulation",
            strategy_name=None,
            horizon=SignalLabelHorizon.SWING_10D,
            material_config_values=altered,
            authority_registrations=authority_regs,
        )
        assert result.material_config_hash != baseline.material_config_hash, (
            f"family path {path} did not change material_config_hash"
        )


# ---------------------------------------------------------------------------
# Different-family config does not fragment current family identity
# ---------------------------------------------------------------------------


def test_different_family_path_does_not_affect_current_family(
    registry: SignalSemanticContractRegistry,
    material_values_with_family: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    baseline = registry.resolve_label(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family="accumulation",
        strategy_name=None,
        horizon=SignalLabelHorizon.SWING_10D,
        material_config_values=material_values_with_family,
        authority_registrations=authority_regs,
    )
    altered = dict(material_values_with_family)
    altered["swing_setups.setups.coiled-spring.enabled"] = False
    result = registry.resolve_label(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family="accumulation",
        strategy_name=None,
        horizon=SignalLabelHorizon.SWING_10D,
        material_config_values=altered,
        authority_registrations=authority_regs,
    )
    assert result.material_config_hash == baseline.material_config_hash


# ---------------------------------------------------------------------------
# Missing declared path raises ValueError
# ---------------------------------------------------------------------------


def test_missing_common_path_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    incomplete = dict(material_values)
    incomplete.pop("signal_engine.classification.strong_min_score")
    with pytest.raises(ValueError, match="missing required material config path"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=incomplete,
            authority_registrations=authority_regs,
        )


def test_missing_family_path_raises(
    registry: SignalSemanticContractRegistry,
    material_values_with_family: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    incomplete = dict(material_values_with_family)
    incomplete.pop("swing_setups.setups.foreign-bounce.enabled")
    with pytest.raises(ValueError, match="missing required material config path"):
        registry.resolve_label(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family="accumulation",
            strategy_name=None,
            horizon=SignalLabelHorizon.SWING_10D,
            material_config_values=incomplete,
            authority_registrations=authority_regs,
        )


# ---------------------------------------------------------------------------
# Undeclared extra values do not change hash
# ---------------------------------------------------------------------------


def test_undeclared_extra_values_ignored(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    baseline = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    with_extra = dict(material_values)
    with_extra["display.some_setting"] = "blue"
    result = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=with_extra,
        authority_registrations=authority_regs,
    )
    assert result.material_config_hash == baseline.material_config_hash


# ---------------------------------------------------------------------------
# Non-finite floats and non-JSON types rejected
# ---------------------------------------------------------------------------


def test_nan_float_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(material_values)
    bad["signal_engine.classification.moderate_min_score"] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=bad,
            authority_registrations=authority_regs,
        )


def test_inf_float_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(material_values)
    bad["signal_engine.classification.moderate_min_score"] = float("inf")
    with pytest.raises(ValueError, match="non-finite"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=bad,
            authority_registrations=authority_regs,
        )


def test_neg_inf_float_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(material_values)
    bad["signal_engine.classification.moderate_min_score"] = float("-inf")
    with pytest.raises(ValueError, match="non-finite"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=bad,
            authority_registrations=authority_regs,
        )


def test_set_object_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(material_values)
    bad["signal_engine.classification.moderate_min_score"] = {"a", "b"}
    with pytest.raises(ValueError, match="unsupported type"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=bad,
            authority_registrations=authority_regs,
        )


def test_bytes_value_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(material_values)
    bad["signal_engine.classification.moderate_min_score"] = b"45"
    with pytest.raises(ValueError, match="unsupported type"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=bad,
            authority_registrations=authority_regs,
        )


def test_bytearray_value_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(material_values)
    bad["signal_engine.classification.moderate_min_score"] = bytearray(b"45")
    with pytest.raises(ValueError, match="unsupported type"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=bad,
            authority_registrations=authority_regs,
        )


# ---------------------------------------------------------------------------
# Strategy-scope rejection (Finding 2)
# ---------------------------------------------------------------------------


def test_resolve_observation_rejects_non_none_strategy_name(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    with pytest.raises(ValueError, match="strategy-enabled artifacts are unsupported"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name="foreign-accumulation",
            material_config_values=material_values,
            authority_registrations=authority_regs,
        )


def test_resolve_label_rejects_non_none_strategy_name(
    registry: SignalSemanticContractRegistry,
    material_values_with_family: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    with pytest.raises(ValueError, match="strategy-enabled artifacts are unsupported"):
        registry.resolve_label(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family="accumulation",
            strategy_name="bb-mean-reversion",
            horizon=SignalLabelHorizon.SWING_10D,
            material_config_values=material_values_with_family,
            authority_registrations=authority_regs,
        )


# ---------------------------------------------------------------------------
# Authority registration integrity (Finding 4)
# ---------------------------------------------------------------------------


def test_changing_authority_status_changes_hash(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    baseline = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    altered = dict(authority_regs)
    altered["setup_quality"] = EvidenceRegistration(
        evidence_name="setup_quality",
        status=EvidenceAuthorityStatus.LOW_WEIGHT,
        low_weight_cap=0.10,
    )
    result = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=altered,
    )
    assert result.authority_registrations_hash != baseline.authority_registrations_hash


def test_changing_low_weight_cap_changes_hash(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    baseline = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    altered = dict(authority_regs)
    altered["setup_quality"] = EvidenceRegistration(
        evidence_name="setup_quality",
        status=EvidenceAuthorityStatus.PRODUCTION,
        low_weight_cap=0.25,
    )
    result = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=altered,
    )
    assert result.authority_registrations_hash != baseline.authority_registrations_hash


def test_changing_only_promotion_metadata_does_not_change_hash(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    baseline = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    altered = dict(authority_regs)
    altered["setup_quality"] = EvidenceRegistration(
        evidence_name="setup_quality",
        status=EvidenceAuthorityStatus.PRODUCTION,
        low_weight_cap=0.10,
        promoted_by="admin",
        promoted_date="2026-07-18",
        promotion_requires=("metric_a",),
    )
    result = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=altered,
    )
    assert result.authority_registrations_hash == baseline.authority_registrations_hash


def test_missing_authority_registration_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    incomplete = dict(authority_regs)
    incomplete.pop("setup_quality")
    with pytest.raises(ValueError, match="missing required authority registration"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=material_values,
            authority_registrations=incomplete,
        )


def test_undeclared_authority_registrations_ignored(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    baseline = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    extended = dict(authority_regs)
    extended["rogue_authority"] = EvidenceRegistration(
        evidence_name="rogue",
        status=EvidenceAuthorityStatus.PRODUCTION,
        low_weight_cap=0.50,
    )
    extra_result = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=extended,
    )
    assert baseline.authority_registrations_hash == extra_result.authority_registrations_hash


def test_authority_registration_wrong_type_raises_type_error(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(authority_regs)
    bad["setup_quality"] = {"evidence_name": "setup_quality", "status": "PRODUCTION"}  # type: ignore[assignment]
    with pytest.raises(TypeError, match="must be an EvidenceRegistration"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=material_values,
            authority_registrations=bad,
        )


def test_authority_registration_mismatched_evidence_name_raises_value_error(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(authority_regs)
    bad["setup_quality"] = EvidenceRegistration(
        evidence_name="institutional_flow",
        status=EvidenceAuthorityStatus.PRODUCTION,
        low_weight_cap=0.10,
    )
    with pytest.raises(ValueError, match="does not match"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=material_values,
            authority_registrations=bad,
        )


# ---------------------------------------------------------------------------
# Observation dimensions
# ---------------------------------------------------------------------------


def test_observation_omits_label_schema_and_policy_version(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    result = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    assert result.label_schema_version is None
    assert result.execution_label_policy_version is None
    assert result.observation_schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Label dimensions
# ---------------------------------------------------------------------------


def test_label_includes_both_schema_versions_and_policy(
    registry: SignalSemanticContractRegistry,
    material_values_with_family: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    result = registry.resolve_label(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family="accumulation",
        strategy_name=None,
        horizon=SignalLabelHorizon.SWING_10D,
        material_config_values=material_values_with_family,
        authority_registrations=authority_regs,
    )
    assert result.observation_schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    assert result.label_schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION
    assert result.execution_label_policy_version == "swing_10d_v1"


# ---------------------------------------------------------------------------
# Different forward-outcome horizons produce different semantic IDs
# ---------------------------------------------------------------------------


def test_different_horizons_produce_different_semantic_ids(
    registry: SignalSemanticContractRegistry,
    material_values_with_family: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    resolver = SignalArtifactIdentityResolver()

    tactical = registry.resolve_label(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family="accumulation",
        strategy_name=None,
        horizon=SignalLabelHorizon.TACTICAL_3D,
        material_config_values=material_values_with_family,
        authority_registrations=authority_regs,
    )
    swing = registry.resolve_label(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family="accumulation",
        strategy_name=None,
        horizon=SignalLabelHorizon.SWING_10D,
        material_config_values=material_values_with_family,
        authority_registrations=authority_regs,
    )
    tactical_id = resolver.resolve_semantic_compatibility_id(tactical)
    swing_id = resolver.resolve_semantic_compatibility_id(swing)
    assert tactical_id != swing_id


# ---------------------------------------------------------------------------
# Unknown contract rejected
# ---------------------------------------------------------------------------


def test_unknown_contract_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    with pytest.raises(ValueError, match="unknown observation_contract"):
        registry.resolve_observation(
            observation_contract="unknown-contract",
            setup_family=None,
            strategy_name=None,
            material_config_values=material_values,
            authority_registrations=authority_regs,
        )


# ---------------------------------------------------------------------------
# setup_family=None uses common + horizon paths only
# ---------------------------------------------------------------------------


def test_setup_family_none_uses_only_common(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    result = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    assert result.setup_family is None
    assert isinstance(result.material_config_hash, str) and len(result.material_config_hash) == 64


# ---------------------------------------------------------------------------
# Unknown non-None setup_family raises
# ---------------------------------------------------------------------------


def test_unknown_setup_family_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    with pytest.raises(ValueError, match="unknown setup_family"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family="nonexistent",
            strategy_name=None,
            material_config_values=material_values,
            authority_registrations=authority_regs,
        )


# ---------------------------------------------------------------------------
# Unknown/missing evaluation horizon fails closed
# ---------------------------------------------------------------------------


def test_missing_default_horizon_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    incomplete = dict(material_values)
    incomplete.pop("signal_engine.alpha_trigger.default_horizon")
    with pytest.raises(ValueError, match="missing required material config path"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=incomplete,
            authority_registrations=authority_regs,
        )


def test_non_string_default_horizon_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(material_values)
    bad["signal_engine.alpha_trigger.default_horizon"] = 123
    with pytest.raises(ValueError, match="must be a string"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=bad,
            authority_registrations=authority_regs,
        )


def test_unknown_default_horizon_raises(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    bad = dict(material_values)
    bad["signal_engine.alpha_trigger.default_horizon"] = "UNKNOWN_HORIZON"
    with pytest.raises(ValueError, match="unknown evaluation horizon"):
        registry.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=bad,
            authority_registrations=authority_regs,
        )


# ---------------------------------------------------------------------------
# No ticker, session, invocation, or revision in API
# ---------------------------------------------------------------------------


def test_api_has_no_ticker_session_invocation_revision(
    registry: SignalSemanticContractRegistry,
    material_values: dict[str, object],
    authority_regs: dict[str, EvidenceRegistration],
):
    result = registry.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=material_values,
        authority_registrations=authority_regs,
    )
    canonical = result.to_canonical_dict()
    for forbidden in ("ticker", "session", "invocation", "revision"):
        assert forbidden not in str(canonical)


# ---------------------------------------------------------------------------
# Real ACCUMULATION_DISCOVERY manifest — test-only owned-document loader.
# Reads the eight owned config/*.yaml files directly; production code never
# loads YAML here.
# ---------------------------------------------------------------------------


def _load_owned_config_documents() -> dict[str, Mapping[str, object]]:
    accumulation_doc = yaml.safe_load(
        Path("config/accumulation_screener.yaml").read_text()
    )
    signal_doc = yaml.safe_load(Path("config/signal_engine.yaml").read_text())
    swing_doc = yaml.safe_load(Path("config/swing_setups.yaml").read_text())
    institutional_doc = yaml.safe_load(
        Path("config/institutional_accumulation.yaml").read_text()
    )
    ticker_profile_doc = yaml.safe_load(Path("config/ticker_profile.yaml").read_text())
    sector_context_doc = yaml.safe_load(Path("config/sector_context.yaml").read_text())
    company_quality_doc = yaml.safe_load(
        Path("config/company_quality_context.yaml").read_text()
    )
    market_context_doc = yaml.safe_load(
        Path("config/market_context_engine.yaml").read_text()
    )
    return {
        "accumulation_screener": accumulation_doc["accumulation_screener"],
        "signal_engine": signal_doc["signal_engine"],
        "swing_setups": swing_doc,
        "institutional_accumulation": institutional_doc["institutional_accumulation"],
        "ticker_profile": ticker_profile_doc["ticker_profile"],
        # Rootless documents map the whole document to the logical root.
        "sector_context": sector_context_doc,
        "company_quality_context": company_quality_doc,
        "market_context_engine": market_context_doc["market_context_engine"],
    }


def _resolve_logical_path(
    documents: Mapping[str, Mapping[str, object]],
    path: str,
) -> object:
    segments = path.split(".")
    root_key = segments[0]
    assert root_key in documents, (
        f"unknown owned document root {root_key!r} while resolving {path!r}"
    )
    node: object = documents[root_key]
    consumed = [root_key]
    for segment in segments[1:]:
        assert isinstance(node, Mapping), (
            f"cannot traverse segment {segment!r}: "
            f"{'.'.join(consumed)!r} is not a mapping, while resolving {path!r}"
        )
        assert segment in node, (
            f"missing segment {segment!r} while resolving {path!r} "
            f"(resolved so far: {'.'.join(consumed)!r})"
        )
        node = node[segment]
        consumed.append(segment)
    return node


def _material_values_for(
    definition: SemanticContractDefinition,
    *,
    setup_family: str | None,
    documents: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    if documents is None:
        documents = _load_owned_config_documents()
    default_horizon = _resolve_logical_path(
        documents, "signal_engine.alpha_trigger.default_horizon",
    )
    assert isinstance(default_horizon, str)
    paths = definition.material_paths_for(
        setup_family=setup_family,
        evaluation_horizon=default_horizon,
    )
    return {path: _resolve_logical_path(documents, path) for path in paths}


def _real_authority_registrations() -> dict[str, EvidenceRegistration]:
    signal_doc = yaml.safe_load(Path("config/signal_engine.yaml").read_text())
    resolved_config = resolve_signal_engine_config(signal_doc)
    return dict(resolved_config.alpha_trigger.evidence_registrations)


def _set_nested(documents: dict, path: str, value: object) -> None:
    segments = path.split(".")
    node = documents[segments[0]]
    for segment in segments[1:-1]:
        node = node[segment]
    node[segments[-1]] = value


def _mutated_documents(overrides: dict[str, object]) -> dict[str, Mapping[str, object]]:
    documents = deepcopy(_load_owned_config_documents())
    for path, value in overrides.items():
        _set_nested(documents, path, value)
    return documents


def _resolve_material_hash(
    reg: SignalSemanticContractRegistry,
    *,
    setup_family: str | None,
    values: Mapping[str, object],
) -> str:
    result = reg.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=setup_family,
        strategy_name=None,
        material_config_values=values,
        authority_registrations=_real_authority_registrations(),
    )
    return result.material_config_hash


def _material_hash_for(
    registry: SignalSemanticContractRegistry,
    *,
    setup_family: str | None,
    documents: Mapping[str, Mapping[str, object]] | None = None,
) -> str:
    values = _material_values_for(
        registry.definition, setup_family=setup_family, documents=documents,
    )
    return _resolve_material_hash(registry, setup_family=setup_family, values=values)


def test_real_accumulation_discovery_none_family_resolves():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    result = reg.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=None,
        strategy_name=None,
        material_config_values=values,
        authority_registrations=_real_authority_registrations(),
    )
    assert result.setup_family is None
    assert isinstance(result.material_config_hash, str) and len(result.material_config_hash) == 64


@pytest.mark.parametrize(
    "family",
    ["accumulation", "breakout", "pullback", "foreign_bounce", "mean_reversion"],
)
def test_real_accumulation_discovery_every_production_family_resolves(family: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=family)
    result = reg.resolve_observation(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        setup_family=family,
        strategy_name=None,
        material_config_values=values,
        authority_registrations=_real_authority_registrations(),
    )
    assert result.setup_family == family


def test_real_every_selected_path_exists_in_owned_documents():
    documents = _load_owned_config_documents()
    default_horizon = _resolve_logical_path(
        documents, "signal_engine.alpha_trigger.default_horizon",
    )
    families: tuple[str | None, ...] = (
        None, "accumulation", "breakout", "pullback", "foreign_bounce", "mean_reversion",
    )
    for family in families:
        paths = ACCUMULATION_DISCOVERY.material_paths_for(
            setup_family=family, evaluation_horizon=default_horizon,
        )
        for path in paths:
            _resolve_logical_path(documents, path)


def test_real_accumulation_discovery_rejects_removed_family():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    with pytest.raises(ValueError, match="unknown setup_family"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family="confirmation",
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


# ---------------------------------------------------------------------------
# Finding 1 — named-setup gate config is common family-resolution material
# ---------------------------------------------------------------------------


def test_real_smart_money_confirmed_gate_changes_hash_when_family_none():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "swing_setups.setups.smart-money-confirmed.gates.min_smart_share_pct": 55.0,
    })
    changed = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed != baseline


def test_real_coiled_spring_gate_changes_hash_for_accumulation_observation():
    """coiled-spring config is common material_evaluated for family resolution
    even though the primary family selected is accumulation, because
    matched_setup_families is persisted regardless of the primary family."""
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family="accumulation")
    mutated = _mutated_documents({
        "swing_setups.setups.coiled-spring.gates.max_bb_width_pctile": 0.35,
    })
    changed = _material_hash_for(reg, setup_family="accumulation", documents=mutated)
    assert changed != baseline


def test_real_pullback_continuation_gate_changes_hash_for_breakout_observation():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family="breakout")
    mutated = _mutated_documents({
        "swing_setups.setups.pullback-continuation.gates.min_rsi": 45.0,
    })
    changed = _material_hash_for(reg, setup_family="breakout", documents=mutated)
    assert changed != baseline


def test_real_accumulation_phase_requirement_changes_accumulation_and_foreign_bounce_hashes():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    mutated = _mutated_documents({
        "swing_setups.setup_phase.requirements.accumulation.enter_phases": ["COMPRESSION"],
    })
    for family in ("accumulation", "foreign_bounce"):
        baseline = _material_hash_for(reg, setup_family=family)
        changed = _material_hash_for(reg, setup_family=family, documents=mutated)
        assert changed != baseline, family


def test_real_pullback_phase_requirement_does_not_change_accumulation_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family="accumulation")
    mutated = _mutated_documents({
        "swing_setups.setup_phase.requirements.pullback.enter_phases": ["COMPRESSION"],
    })
    unchanged = _material_hash_for(reg, setup_family="accumulation", documents=mutated)
    assert unchanged == baseline


def test_real_no_named_setup_path_remains_in_family_scoped_tuple():
    for family, paths in ACCUMULATION_DISCOVERY.material_config_paths_by_setup_family:
        for path in paths:
            assert "swing_setups.setups." not in path, (
                f"family {family!r} still owns named-setup path {path!r}; "
                "named-setup gates must be common material, not family-scoped"
            )


# ---------------------------------------------------------------------------
# Alpha/Trigger evaluation-horizon scoping (retained from Slice 5)
# ---------------------------------------------------------------------------


def test_real_selected_swing_route_fraction_changes_hash_when_default_horizon_swing():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "signal_engine.alpha_trigger.route_fractions.SWING_10D.setup_quality.alpha_fraction": 0.05,
    })
    changed = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed != baseline


def test_real_tactical_route_fraction_ignored_when_default_horizon_swing():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "signal_engine.alpha_trigger.route_fractions.TACTICAL_3D.setup_quality.alpha_fraction": 0.99,
    })
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


def test_real_changing_default_horizon_to_tactical_changes_hash_and_selects_tactical_paths():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "signal_engine.alpha_trigger.default_horizon": "TACTICAL_3D",
    })
    changed_values = _material_values_for(
        ACCUMULATION_DISCOVERY, setup_family=None, documents=mutated,
    )
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.TACTICAL_3D" in changed_values
    assert "signal_engine.alpha_trigger.horizon_alpha_weights.SWING_10D" not in changed_values
    changed = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed != baseline


def test_real_missing_selected_horizon_path_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values.pop(
        "signal_engine.alpha_trigger.route_fractions.SWING_10D.setup_quality.alpha_fraction"
    )
    with pytest.raises(ValueError, match="missing required material config path"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_unknown_configured_default_horizon_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values["signal_engine.alpha_trigger.default_horizon"] = "UNKNOWN_HORIZON"
    with pytest.raises(ValueError, match="unknown evaluation horizon"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


# ---------------------------------------------------------------------------
# Finding 3 — every real declared path affects the hash, exhaustively
# ---------------------------------------------------------------------------


_UNORDERED_NORMALIZATION_PATHS: frozenset[str] = frozenset(
    ACCUMULATION_DISCOVERY.unordered_upper_string_config_paths
    + ACCUMULATION_DISCOVERY.unordered_lower_string_config_paths
)
_UNORDERED_INTEGER_NORMALIZATION_PATHS: frozenset[str] = frozenset(
    ACCUMULATION_DISCOVERY.unordered_integer_config_paths
)
_COMMODITY_NORMALIZATION_PATHS: frozenset[str] = frozenset(
    ACCUMULATION_DISCOVERY.commodity_component_config_paths
)


def _mutate_value(value: object, *, path: str) -> object:
    """Deterministically mutate a declared value so identity must change.

    Paths declared as unordered-string-collection or unordered-integer
    normalization targets are mutated by membership change (append a
    distinct sentinel), not by reordering — canonicalization makes
    reordering/case/whitespace/duplicate differences hash-invariant by
    design, so a reorder-based mutation would incorrectly assert that a
    no-op changes identity. Commodity-component paths are mutated by
    changing one component's weight, preserving both tickers' "KO"
    substring role classification so the mutation stays a valid two-leg
    (cpo, coal) component list.
    """
    if path in _UNORDERED_NORMALIZATION_PATHS:
        assert isinstance(value, list)
        return list(value) + ["ZZZ_SENTINEL_MEMBER_NOT_PRESENT"]
    if path in _UNORDERED_INTEGER_NORMALIZATION_PATHS:
        assert isinstance(value, list)
        new_member = (max(value) + 1000) if value else 999999
        return list(value) + [new_member]
    if path in _COMMODITY_NORMALIZATION_PATHS:
        assert isinstance(value, list)
        mutated_components = deepcopy(value)
        mutated_components[0]["weight"] = mutated_components[0]["weight"] + 0.001
        return mutated_components
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 0.125
    if isinstance(value, str):
        return value + "__changed"
    if isinstance(value, list):
        if len(value) > 1:
            return list(reversed(value))
        return list(value) + ["__sentinel__"]
    if isinstance(value, dict):
        mutated = dict(value)
        first_key = next(iter(mutated))
        mutated[first_key] = _mutate_value(
            mutated[first_key], path=f"{path}.{first_key}",
        )
        return mutated
    if value is None:
        return "__sentinel__"
    raise AssertionError(f"unhandled type for deterministic mutation: {type(value)}")


@pytest.mark.parametrize("evaluation_horizon", ["TACTICAL_3D", "SWING_10D", "ACCUM_20D"])
@pytest.mark.parametrize(
    "setup_family",
    [None, "accumulation", "breakout", "pullback", "foreign_bounce", "mean_reversion"],
)
def test_real_every_selected_material_path_changes_hash(
    setup_family: str | None, evaluation_horizon: str,
):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    documents = _mutated_documents({
        "signal_engine.alpha_trigger.default_horizon": evaluation_horizon,
    })
    baseline_values = _material_values_for(
        ACCUMULATION_DISCOVERY, setup_family=setup_family, documents=documents,
    )
    baseline_hash = _resolve_material_hash(
        reg, setup_family=setup_family, values=baseline_values,
    )
    selected_paths = ACCUMULATION_DISCOVERY.material_paths_for(
        setup_family=setup_family, evaluation_horizon=evaluation_horizon,
    )
    for path in selected_paths:
        if path == "signal_engine.alpha_trigger.default_horizon":
            # Handled separately — mutating it to an unknown horizon must
            # fail closed rather than merely change the hash.
            continue
        mutated_values = dict(baseline_values)
        mutated_values[path] = _mutate_value(mutated_values[path], path=path)
        mutated_hash = _resolve_material_hash(
            reg, setup_family=setup_family, values=mutated_values,
        )
        assert mutated_hash != baseline_hash, (
            f"path {path!r} (family={setup_family!r}, horizon={evaluation_horizon!r}) "
            "did not change material_config_hash"
        )


# ---------------------------------------------------------------------------
# Unordered-collection canonicalization (Step 2)
# ---------------------------------------------------------------------------


def test_real_reordered_broker_codes_same_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = documents["accumulation_screener"]["broker_quality"]["smart_money"]["brokers"]
    mutated = _mutated_documents({
        "accumulation_screener.broker_quality.smart_money.brokers": list(reversed(original)),
    })
    reordered_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert reordered_hash == baseline


def test_real_broker_codes_case_whitespace_and_duplicates_same_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "accumulation_screener.broker_quality.noise.brokers": [
            " yp ", "PD", "pd", "XL", "xc", "XC",
        ],
    })
    result_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert result_hash == baseline


def test_real_reordered_trusted_volume_sources_same_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = documents["swing_setups"]["setup_phase"]["volume_trigger"][
        "trusted_benchmark_volume_sources"
    ]
    mutated = _mutated_documents({
        "swing_setups.setup_phase.volume_trigger.trusted_benchmark_volume_sources": (
            list(reversed(original))
        ),
    })
    result_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert result_hash == baseline


def test_real_adding_broker_changes_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "accumulation_screener.broker_quality.noise.brokers": ["YP", "PD", "XL", "XC", "NEW"],
    })
    changed_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed_hash != baseline


def test_real_removing_broker_changes_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "accumulation_screener.broker_quality.noise.brokers": ["YP", "PD", "XL"],
    })
    changed_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed_hash != baseline


def test_real_adding_trusted_volume_source_changes_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "swing_setups.setup_phase.volume_trigger.trusted_benchmark_volume_sources": [
            "stockbit", "idx", "bloomberg",
        ],
    })
    changed_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed_hash != baseline


def test_real_reversing_required_sequence_changes_hash():
    """required_sequence is a state-machine order, deliberately excluded from
    normalization — reversing it must change identity."""
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family="accumulation")
    mutated = _mutated_documents({
        "swing_setups.setup_phase.requirements.accumulation.required_sequence": [
            "BREAKOUT_CONFIRMATION", "COMPRESSION", "ACCUMULATION",
        ],
    })
    changed_hash = _material_hash_for(reg, setup_family="accumulation", documents=mutated)
    assert changed_hash != baseline


def test_real_non_string_broker_code_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values["accumulation_screener.broker_quality.noise.brokers"] = ["YP", 123]
    with pytest.raises(ValueError, match="must be a string"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_empty_string_after_normalization_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values["accumulation_screener.broker_quality.noise.brokers"] = ["YP", "   "]
    with pytest.raises(ValueError, match="must not be empty"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_non_list_unordered_path_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values["accumulation_screener.broker_quality.noise.brokers"] = "YP"
    with pytest.raises(ValueError, match="must be a list or tuple"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


# ---------------------------------------------------------------------------
# Unordered integer-window normalization
# ---------------------------------------------------------------------------

_INTEGER_WINDOW_PATHS = (
    "institutional_accumulation.windows.broker_consistency_days",
    "institutional_accumulation.windows.cnfb_bearish_distribution",
    "institutional_accumulation.windows.cnfb_bullish_accumulation",
)


@pytest.mark.parametrize("path", _INTEGER_WINDOW_PATHS)
def test_real_reordering_integer_window_preserves_hash(path: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = _resolve_logical_path(documents, path)
    mutated = _mutated_documents({path: list(reversed(original))})
    reordered_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert reordered_hash == baseline


@pytest.mark.parametrize("path", _INTEGER_WINDOW_PATHS)
def test_real_duplicating_integer_window_changes_hash(path: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = _resolve_logical_path(documents, path)
    mutated = _mutated_documents({path: list(original) + [original[0]]})
    duplicated_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert duplicated_hash != baseline


@pytest.mark.parametrize("path", _INTEGER_WINDOW_PATHS)
def test_real_adding_integer_window_changes_hash(path: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = _resolve_logical_path(documents, path)
    new_window = max(original) + 100
    mutated = _mutated_documents({path: list(original) + [new_window]})
    changed_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed_hash != baseline


@pytest.mark.parametrize("path", _INTEGER_WINDOW_PATHS)
def test_real_removing_integer_window_changes_hash(path: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = _resolve_logical_path(documents, path)
    mutated = _mutated_documents({path: list(original)[:-1]})
    changed_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed_hash != baseline


@pytest.mark.parametrize("path", _INTEGER_WINDOW_PATHS)
def test_real_string_integer_window_member_fails_closed(path: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    original = values[path]
    values[path] = list(original) + ["20"]
    with pytest.raises(ValueError, match="must be an int"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


@pytest.mark.parametrize("path", _INTEGER_WINDOW_PATHS)
def test_real_float_integer_window_member_fails_closed(path: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    original = values[path]
    values[path] = list(original) + [20.5]
    with pytest.raises(ValueError, match="must be an int"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


@pytest.mark.parametrize("path", _INTEGER_WINDOW_PATHS)
def test_real_boolean_integer_window_member_fails_closed(path: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    original = values[path]
    values[path] = list(original) + [True]
    with pytest.raises(ValueError, match="must be an int"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_non_list_integer_window_path_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values["institutional_accumulation.windows.cnfb_bullish_accumulation"] = 20
    with pytest.raises(ValueError, match="must be a list or tuple"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


# ---------------------------------------------------------------------------
# Commodity component role normalization
# ---------------------------------------------------------------------------

_COMMODITY_PATH = "market_context_engine.factors.commodity_composite.components"


def test_real_reversing_commodity_components_preserves_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = _resolve_logical_path(documents, _COMMODITY_PATH)
    mutated = _mutated_documents({_COMMODITY_PATH: list(reversed(original))})
    reversed_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert reversed_hash == baseline


def test_real_changing_commodity_ticker_changes_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = deepcopy(_resolve_logical_path(documents, _COMMODITY_PATH))
    # Keep the "KO" substring so the component's runtime role classification
    # (cpo) is unchanged — only the ticker spelling itself must move the hash.
    cpo_component = next(c for c in original if "KO" in c["ticker"])
    cpo_component["ticker"] = "KO2=F"
    mutated = _mutated_documents({_COMMODITY_PATH: original})
    changed_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed_hash != baseline


def test_real_changing_commodity_weight_changes_hash():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    documents = _load_owned_config_documents()
    original = deepcopy(_resolve_logical_path(documents, _COMMODITY_PATH))
    original[0]["weight"] = original[0]["weight"] + 0.05
    mutated = _mutated_documents({_COMMODITY_PATH: original})
    changed_hash = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert changed_hash != baseline


def test_real_commodity_missing_cpo_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = [{"ticker": "MTF=F", "weight": 0.40}]
    with pytest.raises(ValueError, match="missing required 'cpo' role component"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_commodity_missing_coal_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = [{"ticker": "KO=F", "weight": 0.60}]
    with pytest.raises(ValueError, match="missing required 'coal' role component"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_commodity_duplicate_cpo_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = [
        {"ticker": "KO=F", "weight": 0.60},
        {"ticker": "KO2=F", "weight": 0.10},
        {"ticker": "MTF=F", "weight": 0.30},
    ]
    with pytest.raises(ValueError, match="duplicate 'cpo' role component"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_commodity_duplicate_coal_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = [
        {"ticker": "KO=F", "weight": 0.60},
        {"ticker": "MTF=F", "weight": 0.25},
        {"ticker": "NCF=F", "weight": 0.15},
    ]
    with pytest.raises(ValueError, match="duplicate 'coal' role component"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_commodity_non_mapping_item_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = ["not-a-mapping"]
    with pytest.raises(ValueError, match="must be a mapping"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_commodity_unsupported_key_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = [
        {"ticker": "KO=F", "weight": 0.60},
        {"ticker": "MTF=F", "weight": 0.40, "extra_key": "unsupported"},
    ]
    with pytest.raises(ValueError, match="unsupported keys"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_commodity_empty_ticker_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = [
        {"ticker": "   ", "weight": 0.60},
        {"ticker": "MTF=F", "weight": 0.40},
    ]
    with pytest.raises(ValueError, match="must be a non-empty string"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_commodity_boolean_weight_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = [
        {"ticker": "KO=F", "weight": True},
        {"ticker": "MTF=F", "weight": 0.40},
    ]
    with pytest.raises(ValueError, match="must be a finite int or float"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


def test_real_commodity_non_finite_weight_fails_closed():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    values = _material_values_for(ACCUMULATION_DISCOVERY, setup_family=None)
    values[_COMMODITY_PATH] = [
        {"ticker": "KO=F", "weight": float("inf")},
        {"ticker": "MTF=F", "weight": 0.40},
    ]
    with pytest.raises(ValueError, match="non-finite"):
        reg.resolve_observation(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            setup_family=None,
            strategy_name=None,
            material_config_values=values,
            authority_registrations=_real_authority_registrations(),
        )


# ---------------------------------------------------------------------------
# Runtime-parity tests — tests may import infrastructure parsers directly;
# production application code never does.
# ---------------------------------------------------------------------------


def test_real_commodity_integer_and_float_weight_share_hash():
    """Prove that an integer weight (e.g. 1) and its float equivalent (e.g. 1.0)
    produce the exact same registry hash (i.e. normalized to float before hashing)."""
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    documents = _load_owned_config_documents()
    original = deepcopy(_resolve_logical_path(documents, _COMMODITY_PATH))

    original_int = deepcopy(original)
    original_int[0]["weight"] = 1
    original_int[1]["weight"] = 2

    original_float = deepcopy(original)
    original_float[0]["weight"] = 1.0
    original_float[1]["weight"] = 2.0

    mutated_int = _mutated_documents({_COMMODITY_PATH: original_int})
    mutated_float = _mutated_documents({_COMMODITY_PATH: original_float})

    hash_int = _material_hash_for(reg, setup_family=None, documents=mutated_int)
    hash_float = _material_hash_for(reg, setup_family=None, documents=mutated_float)
    assert hash_int == hash_float


def test_runtime_parity_commodity_components_order_insensitive(tmp_path):
    """load_market_context_config() classifies commodity legs by a "KO"
    ticker substring regardless of list position, so baseline and reversed
    commodity_composite.components YAML must parse to an equal typed
    config — confirming the registry's role-based (not positional)
    normalization matches runtime behavior exactly."""
    base_yaml = """
market_context_engine:
  factors:
    commodity_composite:
      enabled: true
      weight: 0.05
      components:
        - ticker: "KO=F"
          weight: 0.60
        - ticker: "MTF=F"
          weight: 0.40
      thresholds:
        lookback_days: 20
        drawdown_risk_off_pct: -5.0
        rally_risk_on_pct: 5.0
"""
    reversed_yaml = """
market_context_engine:
  factors:
    commodity_composite:
      enabled: true
      weight: 0.05
      components:
        - ticker: "MTF=F"
          weight: 0.40
        - ticker: "KO=F"
          weight: 0.60
      thresholds:
        lookback_days: 20
        drawdown_risk_off_pct: -5.0
        rally_risk_on_pct: 5.0
"""
    base_path = tmp_path / "base_market_context_engine.yaml"
    reversed_path = tmp_path / "reversed_market_context_engine.yaml"
    base_path.write_text(base_yaml)
    reversed_path.write_text(reversed_yaml)

    baseline = load_market_context_config(base_path)
    reversed_config = load_market_context_config(reversed_path)

    assert baseline.commodity == reversed_config.commodity


# ---------------------------------------------------------------------------
# Step 3 — removed non-material paths
# ---------------------------------------------------------------------------


def test_real_ticker_profile_epoch_cadence_is_non_material():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({"ticker_profile.epoch_cadence": "weekly"})
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


@pytest.mark.parametrize(
    "setup_name",
    ["foreign-bounce", "coiled-spring", "smart-money-confirmed", "pullback-continuation"],
)
def test_real_named_setup_entry_authority_is_non_material(setup_name: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    base_documents = _load_owned_config_documents()
    original = base_documents["swing_setups"]["setups"][setup_name]["entry_authority"]
    mutated = _mutated_documents({
        f"swing_setups.setups.{setup_name}.entry_authority": not original,
    })
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


@pytest.mark.parametrize(
    "setup_name",
    ["foreign-bounce", "coiled-spring", "smart-money-confirmed", "pullback-continuation"],
)
def test_real_named_setup_can_enter_from_phases_is_non_material(setup_name: str):
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    base_documents = _load_owned_config_documents()
    original = base_documents["swing_setups"]["setups"][setup_name]["can_enter_from_phases"]
    mutated = _mutated_documents({
        f"swing_setups.setups.{setup_name}.can_enter_from_phases": (
            list(original) + ["SENTINEL_PHASE"]
        ),
    })
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


# ---------------------------------------------------------------------------
# Real non-material paths do not change identity
# ---------------------------------------------------------------------------


def test_real_accumulation_display_threshold_is_non_material():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "accumulation_screener.display.enter_min_foreign_flow_score": 12.0,
    })
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


def test_real_accumulation_sorting_is_non_material():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "accumulation_screener.sorting.primary": "foreign_flow_score",
    })
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


def test_real_archived_regime_conditioning_value_is_non_material():
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "signal_engine.regime_conditioning.neutral.weak_flow_discount": 0.10,
    })
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


def test_real_sector_context_yaml_evidence_status_is_non_material():
    """The builder forces produced sector-context evidence to DIAGNOSTIC
    regardless of this YAML field, so changing it cannot alter produced
    evidence and must not fragment compatibility identity."""
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({
        "sector_context.evidence_status": "PRODUCTION",
    })
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


def test_real_document_metadata_version_is_non_material():
    """swing_setups.yaml's top-level "version"/"name"/"description" document
    metadata is mapped into the owned "swing_setups" root (it is a rootless
    document) but no declared path references it, so changing it must not
    change identity."""
    reg = SignalSemanticContractRegistry(ACCUMULATION_DISCOVERY)
    baseline = _material_hash_for(reg, setup_family=None)
    mutated = _mutated_documents({"swing_setups.version": 999})
    unchanged = _material_hash_for(reg, setup_family=None, documents=mutated)
    assert unchanged == baseline


def test_real_manifest_excludes_removed_paths():
    all_declared = set(ACCUMULATION_DISCOVERY.common_material_config_paths)
    for _family, paths in ACCUMULATION_DISCOVERY.material_config_paths_by_setup_family:
        all_declared |= set(paths)
    for _horizon, paths in ACCUMULATION_DISCOVERY.material_config_paths_by_evaluation_horizon:
        all_declared |= set(paths)
    for forbidden in (
        "accumulation_screener.sorting.primary",
        "accumulation_screener.sorting.secondary",
        "accumulation_screener.sorting.tertiary",
        "accumulation_screener.display.enter_min_foreign_flow_score",
        "signal_engine.missing_data.coverage_warning_missing_factors",
        "signal_engine.enrichment.insider_lookback_days",
        "sector_context.evidence_status",
        "institutional_accumulation.evidence_status",
        "ticker_profile.epoch_cadence",
        "swing_setups.setups.foreign-bounce.entry_authority",
        "swing_setups.setups.foreign-bounce.can_enter_from_phases",
        "swing_setups.setups.coiled-spring.entry_authority",
        "swing_setups.setups.coiled-spring.can_enter_from_phases",
        "swing_setups.setups.smart-money-confirmed.entry_authority",
        "swing_setups.setups.smart-money-confirmed.can_enter_from_phases",
        "swing_setups.setups.pullback-continuation.entry_authority",
        "swing_setups.setups.pullback-continuation.can_enter_from_phases",
    ):
        assert forbidden not in all_declared


def test_real_manifest_excludes_removed_non_operational_scoring_prefixes():
    """signal_engine.scoring.seasonality/analyst/forward_pe were removed
    (RETIRE-LEGACY-SIX-FACTOR-BASELINE Slice 2 findings fix, non-operational —
    no producer ever read them from YAML). No declared active material or
    non-material path may reference them; the resolver rejects them outright."""
    all_declared = set(ACCUMULATION_DISCOVERY.common_material_config_paths)
    for _family, paths in ACCUMULATION_DISCOVERY.material_config_paths_by_setup_family:
        all_declared |= set(paths)
    for _horizon, paths in ACCUMULATION_DISCOVERY.material_config_paths_by_evaluation_horizon:
        all_declared |= set(paths)
    non_material = set(_NON_MATERIAL_EXACT_PATHS) | set(_NON_MATERIAL_PREFIX_REASONS)
    removed_prefixes = (
        "signal_engine.scoring.seasonality",
        "signal_engine.scoring.analyst",
        "signal_engine.scoring.forward_pe",
    )
    for prefix in removed_prefixes:
        assert not any(path.startswith(prefix) for path in all_declared), prefix
        assert not any(path.startswith(prefix) for path in non_material), prefix


def test_real_manifest_retains_accumulation_screener_insider_lookback_days():
    assert "accumulation_screener.derived_features.insider_lookback_days" in (
        ACCUMULATION_DISCOVERY.common_material_config_paths
    )


# ---------------------------------------------------------------------------
# Step 4 — exhaustive YAML-leaf classifier.
#
# Every real leaf across all eight owned YAML documents must be explicitly
# classified as material (declared somewhere in the production manifest) or
# non-material (an explicit, justified test-owned exclusion). This inspects
# the real documents rather than mirroring the production manifest, so
# removing a material declaration without adding a justified exclusion makes
# a previously-declared leaf fall through as unclassified and fail the test.
# ---------------------------------------------------------------------------


def _all_declared_material_paths() -> set[str]:
    declared = set(ACCUMULATION_DISCOVERY.common_material_config_paths)
    for _family, paths in ACCUMULATION_DISCOVERY.material_config_paths_by_setup_family:
        declared |= set(paths)
    for _horizon, paths in ACCUMULATION_DISCOVERY.material_config_paths_by_evaluation_horizon:
        declared |= set(paths)
    return declared


def _flatten_yaml_leaves(
    documents: Mapping[str, Mapping[str, object]],
    declared_material_paths: set[str],
) -> list[str]:
    """Flatten every YAML leaf path.

    Descent stops at any path that exactly matches a declared material path
    — treating it as an atomic declared unit (e.g. a whole list-of-dicts,
    such as market_context_engine.factors.commodity_composite.components) —
    or at a genuine scalar/list leaf. This never invents array-index paths.
    """
    leaves: list[str] = []

    def walk(node: object, path: str) -> None:
        if path in declared_material_paths:
            leaves.append(path)
            return
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
            return
        leaves.append(path)

    for root, doc in documents.items():
        for key, value in doc.items():
            walk(value, f"{root}.{key}")
    return leaves


# Exact-path non-material exclusions. Every entry requires a non-empty,
# specific reason — narrowly scoped, never covering a whole active document
# root.
_NON_MATERIAL_EXACT_PATHS: dict[str, str] = {
    "accumulation_screener.sorting.primary": (
        "display/sort ordering only; does not affect canonical scoring or evidence"
    ),
    "accumulation_screener.sorting.secondary": (
        "display/sort ordering only; does not affect canonical scoring or evidence"
    ),
    "accumulation_screener.sorting.tertiary": (
        "display/sort ordering only; does not affect canonical scoring or evidence"
    ),
    "accumulation_screener.display.enter_min_foreign_flow_score": (
        "CLI/report display threshold only; not read by canonical scoring or evidence"
    ),
    "accumulation_screener.display.watch_min_foreign_flow_score": (
        "CLI/report display threshold only; not read by canonical scoring or evidence"
    ),
    "accumulation_screener.display.coiled_spring_min_foreign_flow_score": (
        "CLI/report display threshold only; not read by canonical scoring or evidence"
    ),
    "accumulation_screener.display.coiled_spring_bb_pctile": (
        "CLI/report display threshold only; not read by canonical scoring or evidence"
    ),
    "signal_engine.enrichment.insider_lookback_days": (
        "self-fetch-only lookback used by SignalEngine._build_signal_context(); "
        "accumulation-discovery calls evaluate_with_context() with a prepared "
        "SignalContext and never triggers self-fetch"
    ),
    "sector_context.evidence_status": (
        "the sector-context builder forces produced evidence to DIAGNOSTIC "
        "regardless of this YAML field, so it cannot alter produced evidence"
    ),
    "ticker_profile.epoch_cadence": (
        "TickerProfileConfig.from_mapping() does not consume it; "
        "TickerProfileClassifier derives the epoch directly from snapshot_date"
    ),
    "swing_setups.version": (
        "document metadata only; swing_setups.yaml is rootless so this is "
        "mapped into the owned root, but no material path references it"
    ),
    "swing_setups.name": (
        "document metadata only; swing_setups.yaml is rootless so this is "
        "mapped into the owned root, but no material path references it"
    ),
    "swing_setups.description": (
        "document metadata only; swing_setups.yaml is rootless so this is "
        "mapped into the owned root, but no material path references it"
    ),
    "swing_setups.setup_phase.thresholds.accumulation_min_flow_score": (
        "kept for potential future wiring; _constructive_phase()'s "
        "accumulation gate uses passed_gates/flow_status instead (see "
        "SetupPhaseThresholdsConfig), not an active lever"
    ),
    "swing_setups.setup_phase.thresholds.accumulation_min_flow_ratio_pct": (
        "kept for potential future wiring; _constructive_phase()'s "
        "accumulation gate uses passed_gates/flow_status instead (see "
        "SetupPhaseThresholdsConfig), not an active lever"
    ),
    "swing_setups.setup_phase.thresholds.breakout_min_volume_ratio": (
        "superseded by volume_trigger.dry_up_max_ratio / expansion_min_ratio "
        "(explicit dry-up + expansion evidence); no longer read by "
        "_constructive_phase(), kept for backward-compatible tuning-bounds "
        "entries only"
    ),
}

for _setup_name in (
    "foreign-bounce", "coiled-spring", "smart-money-confirmed", "pullback-continuation",
):
    _NON_MATERIAL_EXACT_PATHS[f"swing_setups.setups.{_setup_name}.entry_authority"] = (
        "PrimarySetupFamilyResolver._from_screen_evidence() only reads "
        "SetupEvaluation.match and .family; entry_authority is a separate "
        "output-only field never consumed by this resolution path"
    )
    _NON_MATERIAL_EXACT_PATHS[f"swing_setups.setups.{_setup_name}.can_enter_from_phases"] = (
        "PrimarySetupFamilyResolver._from_screen_evidence() only reads "
        "SetupEvaluation.match and .family; can_enter_from_phases is a "
        "separate output-only field never consumed by this resolution path"
    )

# Narrowly named prefix exclusions — never an entire active document root.
_NON_MATERIAL_PREFIX_REASONS: dict[str, str] = {
    "signal_engine.regime_conditioning.": (
        "archived Stage 5 diagnostic; legacy_conditioned_score does not affect "
        "canonical assessment.score, decision_policy is the canonical regime gate"
    ),
    "signal_engine.alpha_trigger.evidence_registrations.": (
        "resolved into EvidenceRegistration objects and hashed via the separate "
        "authority_registrations_hash mechanism (resolve_signal_engine_config + "
        "_hash_authority_registrations), not via material_config_paths"
    ),
    "signal_engine.decision_policy.setup_regime_policy.coiled_spring.": (
        "keyed by setup name, not by the normalized family DecisionPolicyService "
        "looks up (breakout); PrimarySetupFamilyResolver reports "
        "family='breakout', never 'coiled_spring'"
    ),
    "signal_engine.decision_policy.setup_regime_policy.smart_money_confirmed.": (
        "keyed by setup name; its normalized family 'confirmation' was removed "
        "from accumulation-discovery's supported family set entirely"
    ),
    "signal_engine.decision_policy.setup_regime_policy.pullback_continuation.": (
        "keyed by setup name, not by the normalized family DecisionPolicyService "
        "looks up (pullback); PrimarySetupFamilyResolver reports "
        "family='pullback', never 'pullback_continuation'"
    ),
    "swing_setups.setup_phase.requirements.confirmation.": (
        "family 'confirmation' was removed from accumulation-discovery's "
        "supported family set; PrimarySetupFamilyResolver never resolves to it "
        "for this contract"
    ),
}


def _classify_leaf(
    path: str,
    declared_material_paths: set[str],
    non_material_exact: Mapping[str, str],
    non_material_prefixes: Mapping[str, str],
) -> str:
    """Classify one YAML leaf path.

    Returns "material", "non_material", "conflict" (declared as both),
    "unjustified_exclusion" (excluded with an empty reason), or
    "unclassified" (neither declared nor excluded).
    """
    is_material = path in declared_material_paths
    exact_reason = non_material_exact.get(path)
    prefix_reason = next(
        (
            reason for prefix, reason in non_material_prefixes.items()
            if path.startswith(prefix)
        ),
        None,
    )
    is_non_material = exact_reason is not None or prefix_reason is not None
    if is_material and is_non_material:
        return "conflict"
    if is_material:
        return "material"
    if is_non_material:
        reason = exact_reason if exact_reason is not None else prefix_reason
        if not reason or not reason.strip():
            return "unjustified_exclusion"
        return "non_material"
    return "unclassified"


def test_non_material_exclusions_have_non_empty_reasons():
    for path, reason in _NON_MATERIAL_EXACT_PATHS.items():
        assert reason.strip(), f"{path} has an empty exclusion reason"
    for prefix, reason in _NON_MATERIAL_PREFIX_REASONS.items():
        assert reason.strip(), f"{prefix} has an empty exclusion reason"


def test_every_real_yaml_leaf_is_explicitly_classified():
    documents = _load_owned_config_documents()
    declared = _all_declared_material_paths()
    leaves = _flatten_yaml_leaves(documents, declared)
    failures: list[tuple[str, str]] = []
    for path in leaves:
        classification = _classify_leaf(
            path, declared, _NON_MATERIAL_EXACT_PATHS, _NON_MATERIAL_PREFIX_REASONS,
        )
        if classification not in ("material", "non_material"):
            failures.append((path, classification))
    assert not failures, (
        "unclassified or conflicting YAML leaves found (path, classification):\n"
        + "\n".join(f"  {p}: {c}" for p, c in failures)
    )


def test_classification_helper_reports_failure_for_unclassified_leaf():
    """A synthetic leaf that is neither declared material nor covered by an
    exclusion must be reported as unclassified by the helper itself."""
    declared = {"root.known.material"}
    result = _classify_leaf("root.totally.unknown.leaf", declared, {}, {})
    assert result == "unclassified"


def test_classification_helper_reports_conflict_for_material_and_excluded_leaf():
    declared = {"root.a.b"}
    result = _classify_leaf(
        "root.a.b", declared, {"root.a.b": "some reason"}, {},
    )
    assert result == "conflict"


def test_classification_helper_reports_unjustified_exclusion_for_empty_reason():
    result = _classify_leaf("root.a.b", set(), {"root.a.b": ""}, {})
    assert result == "unjustified_exclusion"


def test_classification_helper_classifies_material_leaf():
    declared = {"root.a.b"}
    result = _classify_leaf("root.a.b", declared, {}, {})
    assert result == "material"


def test_classification_helper_classifies_non_material_leaf_by_prefix():
    result = _classify_leaf(
        "root.archived.value", set(), {}, {"root.archived.": "archived diagnostic"},
    )
    assert result == "non_material"

