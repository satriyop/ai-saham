"""ADR-068 §1 — the authoritative accumulation cohort identity fold.

Covers the three-part composition itself: that identity is exactly the
behavioural probe digest, the ADR-059 nine-row snapshot payload digest, and
``ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION`` — nothing else — that each
axis moves it on its own, that the fold is deterministic, that it fails closed
rather than degrading, and that pre-open identity is untouched by any of it.

``test_behavioral_probe_harness`` proves the probe digest is a trustworthy
measurement and that it reaches identity through one path. This module proves
the fold that consumes it is the right fold.
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace

import pytest

import src.application.services.behavioral_cohort_identity as identity_module
from src.application.services.accumulation_policy_snapshot_payloads import (
    build_all_accumulation_policy_payloads,
)
from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
)
from src.application.services.behavioral_cohort_identity import (
    BEHAVIORAL_ACCUMULATION_COMPATIBILITY_CONTRACT_ID,
    compute_policy_snapshot_set_digest,
    resolve_accumulation_cohort_identity,
    resolve_accumulation_cohort_identity_from_payloads,
)
from src.application.services.behavioral_probe_runner import (
    compute_behavioral_probe_digest,
)
from src.application.services.pre_open_observation_payload import (
    compute_pre_open_semantic_compatibility_id,
)
from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
    SignalClassificationConfig,
    SignalEngineConfig,
)
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.rules.risk_gate import UnevaluableGateAction, UnevaluableGatePolicy
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    LearningContractError,
    canonical_json,
)
from src.domain.value_objects.signal_artifact_schema import (
    ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION,
)


def _hard_filters(**overrides: object) -> AccumulationScreenHardFilterPolicy:
    base = dict(
        min_market_cap_idr=0,
        min_piotroski=0,
        min_accum_score=0.0,
        min_accum_score_enabled=True,
        min_signal_score=45.0,
        min_signal_score_enabled=False,
    )
    base.update(overrides)
    return AccumulationScreenHardFilterPolicy(**base)  # type: ignore[arg-type]


def _payloads(**overrides: object) -> dict:
    kwargs: dict = dict(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate(), LiquidityGate()],
        execution_gates=[BandarGate()],
        hard_filter_policy=_hard_filters(),
        unevaluable_gate_policy=UnevaluableGatePolicy(),
    )
    kwargs.update(overrides)
    return dict(build_all_accumulation_policy_payloads(**kwargs))


def test_identity_material_is_exactly_the_three_adr_068_parts() -> None:
    """The fold, recomputed independently from its three declared inputs.

    Written as an explicit reconstruction rather than a frozen literal so the
    assertion states *what the material is*. A fourth part, a dropped part, or a
    reordered fold all fail here; a legitimate axis movement does not, because
    the expected value moves with it.
    """
    payloads = _payloads()
    identity = resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=payloads)

    expected_material = canonical_json(
        {
            "contract_id": BEHAVIORAL_ACCUMULATION_COMPATIBILITY_CONTRACT_ID,
            "behavioral_probe_digest": compute_behavioral_probe_digest(),
            "policy_snapshot_payload_digest": compute_policy_snapshot_set_digest(payloads),
            "observation_payload_schema_version": ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION,
        }
    )
    expected = "sha256:" + hashlib.sha256(expected_material.encode("utf-8")).hexdigest()

    assert identity.semantic_compatibility_id.value == expected
    assert identity.behavioral_probe_digest == compute_behavioral_probe_digest()
    assert identity.policy_snapshot_payload_digest == compute_policy_snapshot_set_digest(payloads)
    assert identity.observation_payload_schema_version == (
        ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION
    )


def test_fold_is_deterministic() -> None:
    first = resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=_payloads())
    second = resolve_accumulation_cohort_identity_from_payloads(
        policy_snapshot_payloads=_payloads()
    )
    assert first == second


def test_typed_policy_resolution_matches_payload_resolution() -> None:
    """The typed entry point is the payload entry point plus payload building.

    Guards against the composition root and the fail-closed recompute drifting
    into two different folds.
    """
    from_typed = resolve_accumulation_cohort_identity(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate(), LiquidityGate()],
        execution_gates=[BandarGate()],
        hard_filter_policy=_hard_filters(),
        unevaluable_gate_policy=UnevaluableGatePolicy(),
    )
    from_payloads = resolve_accumulation_cohort_identity_from_payloads(
        policy_snapshot_payloads=_payloads()
    )
    assert from_typed == from_payloads


def test_declared_policy_change_moves_identity() -> None:
    """Axis 2: the ADR-059 snapshot payload digest."""
    base = resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=_payloads())
    changed = resolve_accumulation_cohort_identity_from_payloads(
        policy_snapshot_payloads=_payloads(hard_filter_policy=_hard_filters(min_piotroski=7))
    )
    assert changed.policy_snapshot_payload_digest != base.policy_snapshot_payload_digest
    assert changed.semantic_compatibility_id != base.semantic_compatibility_id
    # The other two axes must not have moved — orthogonality is the point.
    assert changed.behavioral_probe_digest == base.behavioral_probe_digest
    assert changed.observation_payload_schema_version == base.observation_payload_schema_version


def test_payload_schema_bump_moves_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Axis 3: record shape.

    A new payload field can leave every answer identical while breaking a
    consumer, so ADR-068 §8 keeps the schema version in the material.
    """
    base = resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=_payloads())
    monkeypatch.setattr(
        identity_module,
        "ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION",
        ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION + 1,
    )
    bumped = resolve_accumulation_cohort_identity_from_payloads(
        policy_snapshot_payloads=_payloads()
    )
    assert bumped.semantic_compatibility_id != base.semantic_compatibility_id
    assert bumped.policy_snapshot_payload_digest == base.policy_snapshot_payload_digest


def test_engine_behaviour_change_moves_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Axis 1: the code axis — the whole reason ADR-068 exists.

    Under the retired mechanism this required a human to remember a version
    bump. Here the digest is measured, so the fork is automatic.
    """
    base = resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=_payloads())
    monkeypatch.setattr(
        identity_module,
        "compute_behavioral_probe_digest",
        lambda: "f" * 64,
    )
    moved = resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=_payloads())
    assert moved.behavioral_probe_digest == "f" * 64
    assert moved.semantic_compatibility_id != base.semantic_compatibility_id
    assert moved.policy_snapshot_payload_digest == base.policy_snapshot_payload_digest


def test_incomplete_policy_set_fails_closed() -> None:
    """A cohort measured over the wrong policy set is worse than no cohort."""
    short = _payloads()
    short.pop(ACCUMULATION_PRODUCTION_POLICY_IDS[0])
    with pytest.raises(LearningContractError, match="closed v4 policy set"):
        resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=short)

    extra = _payloads()
    extra["unexpected.policy"] = {"anything": 1}
    with pytest.raises(LearningContractError, match="closed v4 policy set"):
        resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=extra)


def test_probe_failure_propagates_rather_than_degrading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No unavailable result, no partial identity.

    Slice 3's shadow resolver degraded a broken probe to a typed unavailable
    value, because everything it produced was diagnostic. That trade inverts
    once the digest *is* identity: minting an id whose code axis was never
    measured would silently pool two engines.
    """

    def _boom() -> str:
        raise RuntimeError("probe harness broken")

    monkeypatch.setattr(identity_module, "compute_behavioral_probe_digest", _boom)
    with pytest.raises(RuntimeError, match="probe harness broken"):
        resolve_accumulation_cohort_identity_from_payloads(policy_snapshot_payloads=_payloads())


def test_snapshot_set_digest_reuses_the_per_row_payload_digest() -> None:
    """One hashing scheme, not two.

    A row's own ``payload_digest`` and its contribution to the cohort must be
    the same number, or the snapshot a reader verifies and the cohort it trusts
    could disagree.
    """
    from src.domain.value_objects.learning_artifacts import policy_snapshot_payload_digest

    payloads = _payloads()
    expected = hashlib.sha256(
        canonical_json(
            {
                policy_id: policy_snapshot_payload_digest(payloads[policy_id])
                for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS
            }
        ).encode("utf-8")
    ).hexdigest()
    assert compute_policy_snapshot_set_digest(payloads) == expected


def test_pre_open_identity_is_untouched_by_adr_068() -> None:
    """Task §4 non-goal: ADR-068 is scoped to ``ACCUMULATION_DISCOVERY``.

    Purpose isolation is asserted two ways. First by value: the pre-open
    compatibility id is pinned to the exact digest it had before this slice, so
    any accidental coupling to the accumulation fold — or to the deleted engine
    version constants, or to the bumped accumulation payload schema version —
    fails here. Second structurally: the pre-open identity module shares no
    material with the accumulation one.
    """
    pre_open = compute_pre_open_semantic_compatibility_id(
        signal_config=PreOpenDirectionalBaselineConfig(),
        classification_config=SignalClassificationConfig(),
        iev_min=0,
        top_n=None,
    )
    # Computed on the pre-slice-4 tree (05af50dd) and re-verified after cutover:
    # byte-identical. This literal is the evidence, not a snapshot of whatever
    # the code happens to produce.
    assert pre_open.value == (
        "sha256:fee5c3f343598f9f0ff83f3a26c1fd18291f91c41f1660cb91c438b19d22917e"
    )

    import src.application.services.pre_open_observation_payload as pre_open_module

    pre_open_source = open(pre_open_module.__file__, encoding="utf-8").read()
    for accumulation_only in (
        "ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION",
        "behavioral_cohort_identity",
        "compute_behavioral_probe_digest",
        "SEMANTIC_ENGINE_VERSION",
        "EVIDENCE_CONTRACT_VERSION",
    ):
        assert accumulation_only not in pre_open_source, (
            f"pre-open identity must not reference {accumulation_only}; ADR-068 "
            "is scoped to ACCUMULATION_DISCOVERY and pre-open keeps its own "
            "mechanism"
        )


def _typed_identity(**overrides: object):
    """Resolve identity through the typed entry point the composition root uses."""
    kwargs: dict = dict(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate(), LiquidityGate()],
        execution_gates=[BandarGate()],
        hard_filter_policy=_hard_filters(),
        unevaluable_gate_policy=UnevaluableGatePolicy(),
    )
    kwargs.update(overrides)
    return resolve_accumulation_cohort_identity(**kwargs)


# One materially different value per declared-policy parameter of
# `resolve_accumulation_cohort_identity`. The sweep below asserts the set of
# keys equals the signature's, so a ninth parameter that nobody threaded into
# the payload builder fails here instead of silently colliding cohorts — the
# exact defect `unevaluable_gate_policy` was.
_DECLARED_POLICY_MUTATIONS: dict[str, object] = {
    "accum_score_policy": replace(
        AccumScorePolicy(), consistency=replace(AccumScorePolicy().consistency, weight=40.0)
    ),
    "signal_engine_config": replace(
        SignalEngineConfig(),
        classification=replace(SignalEngineConfig().classification, strong_min_score=99.0),
    ),
    "structural_gates": [FundamentalGate()],
    "execution_gates": [],
    "hard_filter_policy": _hard_filters(min_piotroski=7),
    "unevaluable_gate_policy": UnevaluableGatePolicy(
        action=UnevaluableGateAction.BLOCK, block_confidence=70
    ),
}


def test_every_declared_policy_parameter_is_swept_by_the_mutation_set() -> None:
    """The sweep must cover the whole signature, not a stale subset."""
    params = set(inspect.signature(resolve_accumulation_cohort_identity).parameters)
    assert params == set(_DECLARED_POLICY_MUTATIONS)


@pytest.mark.parametrize("param", sorted(_DECLARED_POLICY_MUTATIONS))
def test_each_declared_policy_parameter_moves_the_compatibility_id(param: str) -> None:
    """Every declared policy the engines receive must be cohort identity.

    A parameter the engines act on but the snapshot payloads ignore lets two
    deployments that decide differently share one ``compatibility_id``. Only the
    declared-policy axis may move; the probe and schema axes must not.
    """
    base = _typed_identity()
    changed = _typed_identity(**{param: _DECLARED_POLICY_MUTATIONS[param]})

    assert changed.semantic_compatibility_id != base.semantic_compatibility_id, (
        f"{param} does not reach the ADR-059 snapshot payloads"
    )
    assert changed.policy_snapshot_payload_digest != base.policy_snapshot_payload_digest
    assert changed.behavioral_probe_digest == base.behavioral_probe_digest
    assert changed.observation_payload_schema_version == base.observation_payload_schema_version
