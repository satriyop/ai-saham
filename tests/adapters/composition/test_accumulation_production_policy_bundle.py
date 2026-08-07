"""Real-config coverage for the accumulation production policy bundle.

The pure payload tests in
``tests/application/services/test_accumulation_policy_snapshot_payloads.py``
build every gate and policy from bare dataclass defaults, so they prove the
payload builder is a pure function of *hand-made* inputs. Nothing proved it is
a pure function of what production actually loads.

These tests close that gap by resolving the bundle through the exact wiring
``saham research accum backfill`` uses (``load_accumulation_screener_config`` +
``load_swing_policy_config`` + ``resolve_accumulation_production_policy_bundle``)
and feeding the result into ``build_all_accumulation_policy_payloads``. That
path resolves entirely from ``config/*.yaml``: no database, no network, so it
stays inside the offline suite.

Expectations are derived from the resolved bundle objects rather than pinned to
literal config values or recorded digests — config legitimately moves, and a
test that fails on every intentional config edit is noise, not coverage.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.adapters.composition.accumulation_production_policy_bundle import (
    resolve_accumulation_production_policy_bundle,
)
from src.application.services.accumulation_policy_snapshot_payloads import (
    build_all_accumulation_policy_payloads,
)
from src.application.services.accumulation_production_policy_bundle import (
    AccumulationProductionPolicyBundle,
)
from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
)
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.risk_gate import UnevaluableGatePolicy
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
    PRODUCTION_POLICY_ID_RISK_HARD_GATES,
    canonical_json,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.swing_policy_config_loader import load_swing_policy_config

# Reused rather than duplicated: the probe observation is built by the real
# producers (`build_candidate_observation_payload` ->
# `build_session_observation_payload`), so a copy here would drift from the
# producers it is supposed to check. Cross-module test imports are established
# in this suite (see `tests/adapters/tui/agent_board_fixtures.py`).
from tests.application.services.test_accumulation_policy_snapshot_payloads import (
    _assert_declared_paths_resolve,
    _probe_session_observation,
)


def _resolve_real_bundle() -> AccumulationProductionPolicyBundle:
    """Resolve the production bundle exactly as the corpus CLI does.

    Mirrors ``src/adapters/cli/research_accum_backfill_commands.py``. Config
    loaders only — no repository, no provider, no database handle.
    """
    accumulation_config = load_accumulation_screener_config()
    swing_policy = load_swing_policy_config()
    return resolve_accumulation_production_policy_bundle(
        accum_score_policy=accumulation_config.accum_score_policy,
        swing_policy=swing_policy,
        accumulation_screener_config=accumulation_config,
    )


def _payloads_from(bundle: AccumulationProductionPolicyBundle) -> Mapping[str, Mapping[str, Any]]:
    return build_all_accumulation_policy_payloads(
        accum_score_policy=bundle.accum_score_policy,
        signal_engine_config=bundle.signal_engine_config,
        structural_gates=bundle.structural_gates,
        execution_gates=bundle.execution_gates,
        hard_filter_policy=bundle.hard_filter_policy,
        unevaluable_gate_policy=bundle.unevaluable_gate_policy,
    )


def _bare_default_payloads() -> Mapping[str, Mapping[str, Any]]:
    """The same closed set built from bare dataclass defaults.

    This is what every pre-existing payload test asserts against; it exists
    here only as the contrast case for the anti-vacuity check below.
    """
    return build_all_accumulation_policy_payloads(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate()],
        execution_gates=[BandarGate()],
        hard_filter_policy=AccumulationScreenHardFilterPolicy(
            min_market_cap_idr=0,
            min_piotroski=0,
            min_accum_score=0.0,
            min_accum_score_enabled=True,
            min_signal_score=45.0,
            min_signal_score_enabled=False,
        ),
        # The real bundle resolves `surface` from risk_engine.yaml, so this row
        # is byte-identical to the real one today. That is fine: the anti-vacuity
        # check below only requires *some* row to differ.
        unevaluable_gate_policy=UnevaluableGatePolicy(),
    )


def test_real_production_config_builds_the_closed_policy_set() -> None:
    """Real repo config must build all nine rows without raising.

    Row count and the policy-id set are pinned deliberately: the closed set is
    a contract (ADR-059 ``production_policy_snapshot.v4``), not a config value.
    """
    payloads = _payloads_from(_resolve_real_bundle())

    assert set(payloads) == set(ACCUMULATION_PRODUCTION_POLICY_IDS)
    assert len(payloads) == 9


def test_signal_engine_and_snapshot_builder_share_the_resolved_decision_policy_object(
    monkeypatch,
) -> None:
    """No second parse/default may split Action policy from cohort identity."""
    import src.application.services.accumulation_policy_snapshot_payloads as payload_module

    bundle = _resolve_real_bundle()
    seen: list[object] = []
    original = payload_module.build_signal_decision_policy_payload

    def record(policy):
        seen.append(policy)
        return original(policy)

    monkeypatch.setattr(payload_module, "build_signal_decision_policy_payload", record)
    _payloads_from(bundle)
    engine = SignalEngine(config=bundle.signal_engine_config)

    assert seen == [bundle.signal_engine_config.decision_policy]
    assert seen[0] is bundle.signal_engine_config.decision_policy
    assert engine._config.decision_policy is bundle.signal_engine_config.decision_policy
    assert (
        engine._evidence_use_case._config.decision_policy
        is bundle.signal_engine_config.decision_policy
    )


def test_real_production_config_payloads_are_deterministic() -> None:
    """Two independent config loads must produce byte-identical payloads.

    The sibling pure test proves determinism over hand-built defaults. This one
    covers the whole loader -> resolver -> builder path, so a config read that
    leaked ordering, mutation, or environment state would fail here.
    """
    first = _payloads_from(_resolve_real_bundle())
    second = _payloads_from(_resolve_real_bundle())

    for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS:
        assert canonical_json(first[policy_id]) == canonical_json(second[policy_id])


def test_real_production_config_declared_observation_paths_resolve() -> None:
    """Declared observation paths must resolve for the real-config payloads.

    This is the regression guard for the defect class fixed in 503afeb8 and
    746111e9: an ``observation_result_fields`` entry naming a key no producer
    ever writes. Only these two rows are checked because they are the only ones
    whose declared paths land on the candidate/trade-setup part of a session
    observation; the four ``signal.*`` rows point into the signal pack, which a
    candidate-only probe leaves empty, and ``screener.accum.hard_filters`` /
    ``risk.accum.unevaluable_policy`` declare no observation fields at all.
    """
    payloads = _payloads_from(_resolve_real_bundle())
    observation = _probe_session_observation()

    for policy_id in (
        PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
        PRODUCTION_POLICY_ID_RISK_HARD_GATES,
    ):
        _assert_declared_paths_resolve(dict(payloads[policy_id]), observation)


def test_real_production_config_declares_every_resolved_risk_gate() -> None:
    """No gate resolved from ``risk_engine.yaml`` may be dropped by the builder.

    The expectation is computed from the bundle, so adding or removing a gate in
    config keeps this green; silently losing one does not.
    """
    bundle = _resolve_real_bundle()
    payload = _payloads_from(bundle)[PRODUCTION_POLICY_ID_RISK_HARD_GATES]

    components = payload["components"]
    keys = [c["key"] for c in components]
    assert len(keys) == len(set(keys)), f"duplicate gate keys in snapshot row: {keys}"
    assert len(components) == len(bundle.structural_gates) + len(bundle.execution_gates)

    families = [c["order_family"] for c in components]
    assert families.count("structural") == len(bundle.structural_gates)
    assert families.count("execution") == len(bundle.execution_gates)
    # Structural gates short-circuit first, and the declared order is the
    # evaluation order, not an arbitrary re-listing.
    assert families == ["structural"] * len(bundle.structural_gates) + ["execution"] * len(
        bundle.execution_gates
    )
    assert payload["short_circuit"]["order"] == keys


def test_real_production_config_accum_weights_track_the_loaded_policy() -> None:
    """Every weighted component must carry the loaded policy's own value.

    Derived from ``bundle.accum_score_policy``, so a config weight change is
    invisible here, while a builder that hardcoded or dropped a weight fails.
    """
    bundle = _resolve_real_bundle()
    payload = _payloads_from(bundle)[PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS]
    policy = bundle.accum_score_policy

    assert payload["max_score"] == policy.max_score
    assert payload["output_scale"]["max"] == policy.max_score

    by_key = {c["key"]: c for c in payload["components"]}
    for key in ("consistency", "streak", "vwap_discount", "rsi_headroom", "foreign_flow_ratio"):
        component_policy = getattr(policy, key)
        assert by_key[key]["weight"] == component_policy.weight
        assert by_key[key]["enabled"] is component_policy.enabled
    # `bci` is points-based, so it declares no weight — assert that, or a
    # regression that started emitting one would go unnoticed.
    assert "weight" not in by_key["bci"]
    assert by_key["bci"]["cluster_points"] == policy.bci.cluster_points
    assert by_key["bci"]["stable_points"] == policy.bci.stable_points


def test_real_production_config_hard_filters_track_the_loaded_policy() -> None:
    """Hard-filter floors and enabled flags must come from the resolved policy.

    ``hard_filter_policy`` is the one bundle field assembled from two config
    sources (swing policy + accumulation screener config), so it is the most
    likely place for a silently ignored config value.
    """
    bundle = _resolve_real_bundle()
    payload = _payloads_from(bundle)[PRODUCTION_POLICY_ID_HARD_FILTERS]
    policy = bundle.hard_filter_policy
    filters = payload["filters"]

    assert filters["market_cap"]["floor_idr"] == policy.min_market_cap_idr
    assert filters["piotroski"]["floor"] == policy.min_piotroski
    assert filters["accum_score"]["floor"] == policy.min_accum_score
    assert filters["signal_score"]["floor"] == policy.min_signal_score

    assert filters["market_cap"]["enabled"] is (policy.min_market_cap_idr > 0)
    assert filters["piotroski"]["enabled"] is (policy.min_piotroski > 0)
    assert filters["accum_score"]["enabled"] is policy.min_accum_score_enabled
    assert filters["signal_score"]["enabled"] is policy.min_signal_score_enabled


def test_real_production_config_is_not_merely_dataclass_defaults() -> None:
    """Anti-vacuity: the real config must reach the builder at all.

    Without this, every assertion above could be satisfied by a wiring bug that
    quietly handed the builder bare defaults. At the time of writing only
    ``risk.accum.hard_gates`` differs (``risk_engine.yaml`` resolves three
    structural gates where the bare-default fixture uses one); the other seven
    rows are byte-identical to defaults today —
    ``risk.accum.unevaluable_policy`` included, because ``risk_engine.yaml``
    declares the dataclass default (``surface``). The check is therefore phrased as
    "at least one row differs" so an intentional config edit that converges a
    row onto its default does not break it.
    """
    real = _payloads_from(_resolve_real_bundle())
    bare = _bare_default_payloads()

    differing = [
        policy_id
        for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS
        if canonical_json(real[policy_id]) != canonical_json(bare[policy_id])
    ]
    assert differing, (
        "every real-config policy payload equals the bare-dataclass-default "
        "payload; the production config path is not reaching the builder"
    )
