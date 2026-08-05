"""ADR-068 slice 3 — proves the shadow behavioural cohort identity is safe to
observe: stable, attributable, non-fatal on failure, internally consistent,
and silent on the machine-readable channel.

``resolve_shadow_behavioral_cohort_identity`` runs the frozen core probe set
purely as a diagnostic beside the authoritative
``semantic_compatibility_id``. Nothing downstream reads its digests (module
docstring, "Trust ordering"), so the properties worth proving are the ones
that make it *safe to watch on real runs*:

- deterministic and repeatable (no accidental nondeterminism leaking into an
  operator's log diff),
- attributable — a change to the code the probe exercises moves
  ``behavioral_probe_digest`` without moving ``probe_input_digest``, so an
  operator can tell "the engine changed" from "the probe's own frozen inputs
  changed",
- matches the checked-in frozen fixture exactly, so drift is visible in code
  review rather than silently re-baselined,
- transient — a monkeypatched mutation must not survive past the patch,
- passes the authoritative id through untouched (this module must never
  rewrite the value that actually gets persisted),
- fails closed into a typed unavailable result rather than raising, and
- the CLI diagnostic writer never puts a byte on stdout, because
  ``--format json`` stdout is a machine contract this non-authoritative value
  must never enter (see ``_echo_shadow_behavioral_identity`` docstring).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.application.services.behavioral_probe_runner as runner_module
import src.application.services.shadow_behavioral_cohort_identity as shadow_module
from src.adapters.cli.research_accum_backfill_commands import (
    _echo_shadow_behavioral_identity,
)
from src.application.services.engine_bootstrap.risk_config_resolvers import (
    resolve_risk_gates,
)
from src.application.services.shadow_behavioral_cohort_identity import (
    ShadowBehavioralCohortIdentity,
    resolve_shadow_behavioral_cohort_identity,
)
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_PATH = _REPO_ROOT / "tests" / "fixtures" / "behavioral_probe_core.v1.json"

_VALID_COMPATIBILITY_ID = SemanticCompatibilityId(value=f"sha256:{'a' * 64}")


def test_shadow_digests_are_stable_across_repeated_resolutions() -> None:
    first = resolve_shadow_behavioral_cohort_identity(
        authoritative_compatibility_id=_VALID_COMPATIBILITY_ID
    )
    second = resolve_shadow_behavioral_cohort_identity(
        authoritative_compatibility_id=_VALID_COMPATIBILITY_ID
    )

    assert first.is_available, "baseline resolution must succeed against production code"
    assert second.is_available, "repeated resolution must succeed against production code"
    assert first.behavioral_probe_digest == second.behavioral_probe_digest, (
        "behavioral_probe_digest must be byte-identical across repeated calls with unchanged code"
    )
    assert first.probe_input_digest == second.probe_input_digest, (
        "probe_input_digest must be byte-identical across repeated calls with unchanged code"
    )


def test_shadow_behavioral_digest_matches_the_frozen_core_fixture() -> None:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    resolved = resolve_shadow_behavioral_cohort_identity(
        authoritative_compatibility_id=_VALID_COMPATIBILITY_ID
    )

    assert resolved.is_available, "resolution must succeed to compare against the fixture"
    assert resolved.behavioral_probe_digest == fixture["behavioral_probe_digest"], (
        "behavioral_probe_digest drifted from the checked-in frozen core fixture"
    )
    assert resolved.probe_input_digest == fixture["probe_input_digest"], (
        "probe_input_digest drifted from the checked-in frozen core fixture"
    )
    assert resolved.probe_set_id == fixture["core_probe_set_id"], (
        "probe_set_id must name the frozen core probe set the fixture was recorded against"
    )
    assert resolved.projection_contract == fixture["projection_contract"], (
        "projection_contract must match the contract the fixture was recorded under"
    )


def test_shadow_behavioral_digest_moves_when_a_production_constant_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = resolve_shadow_behavioral_cohort_identity(
        authoritative_compatibility_id=_VALID_COMPATIBILITY_ID
    )
    assert baseline.is_available, "baseline resolution must succeed before mutating"

    with monkeypatch.context() as patch:
        patch.setattr(
            runner_module,
            "resolve_risk_gates",
            lambda _cfg: resolve_risk_gates(
                {"risk_engine": {"gates": {"fundamental": {"piotroski_min": 9}}}}
            ),
        )
        mutated = resolve_shadow_behavioral_cohort_identity(
            authoritative_compatibility_id=_VALID_COMPATIBILITY_ID
        )

    assert mutated.is_available, "mutated resolution must still succeed"
    assert mutated.behavioral_probe_digest != baseline.behavioral_probe_digest, (
        "a production risk-gate constant change must move behavioral_probe_digest"
    )
    assert mutated.probe_input_digest == baseline.probe_input_digest, (
        "ADR-068 attribution property: the engine moved but the probe's own "
        "frozen inputs did not, so probe_input_digest must stay put"
    )


def test_shadow_resolution_is_transient_and_restores_production_behaviour() -> None:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    resolved = resolve_shadow_behavioral_cohort_identity(
        authoritative_compatibility_id=_VALID_COMPATIBILITY_ID
    )

    assert resolved.is_available, "resolution after the mutation test must still succeed"
    assert resolved.behavioral_probe_digest == fixture["behavioral_probe_digest"], (
        "the monkeypatch context in the previous test must leave nothing behind; "
        "production behaviour must be fully restored"
    )


def test_shadow_identity_passes_the_authoritative_id_through_untouched() -> None:
    distinctive_id = SemanticCompatibilityId(value="sha256:" + "ab" * 32)

    resolved = resolve_shadow_behavioral_cohort_identity(
        authoritative_compatibility_id=distinctive_id
    )

    assert resolved.authoritative_compatibility_id is distinctive_id, (
        "the shadow must pass the authoritative id through untouched, never "
        "rewriting or re-wrapping the value that is actually persisted"
    )
    assert resolved.authoritative_compatibility_id.value == distinctive_id.value


def test_probe_failure_becomes_a_typed_unavailable_result_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode() -> str:
        raise RuntimeError("probe harness exploded")

    monkeypatch.setattr(shadow_module, "compute_behavioral_probe_digest", _explode)

    resolved = resolve_shadow_behavioral_cohort_identity(
        authoritative_compatibility_id=_VALID_COMPATIBILITY_ID
    )

    assert resolved.is_available is False, "a probe exception must not propagate as a raise"
    assert resolved.behavioral_probe_digest is None
    assert resolved.probe_input_digest is None
    assert resolved.unavailable_reason == "RuntimeError: probe harness exploded"


def test_a_half_populated_shadow_identity_is_rejected() -> None:
    with pytest.raises(ValueError):
        ShadowBehavioralCohortIdentity(
            authoritative_compatibility_id=_VALID_COMPATIBILITY_ID,
            probe_set_id="accum_core.v1",
            projection_contract="accum_behavioral_projection.v1",
            behavioral_probe_digest="deadbeef",
            probe_input_digest="deadbeef",
            unavailable_reason="RuntimeError: should not coexist with digests",
        )

    with pytest.raises(ValueError):
        ShadowBehavioralCohortIdentity(
            authoritative_compatibility_id=_VALID_COMPATIBILITY_ID,
            probe_set_id="accum_core.v1",
            projection_contract="accum_behavioral_projection.v1",
            behavioral_probe_digest=None,
            probe_input_digest=None,
            unavailable_reason=None,
        )


def test_shadow_diagnostic_is_written_to_stderr_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    shadow = ShadowBehavioralCohortIdentity(
        authoritative_compatibility_id=_VALID_COMPATIBILITY_ID,
        probe_set_id="accum_core.v1",
        projection_contract="accum_behavioral_projection.v1",
        behavioral_probe_digest="behavioraldigestvalue",
        probe_input_digest="probeinputdigestvalue",
        unavailable_reason=None,
    )

    _echo_shadow_behavioral_identity(shadow)

    captured = capsys.readouterr()
    assert captured.out == "", (
        "the shadow diagnostic must never write to stdout: --format json stdout "
        "is a machine contract this non-authoritative value must not enter"
    )
    assert _VALID_COMPATIBILITY_ID.value in captured.err
    assert "behavioraldigestvalue" in captured.err
    assert "probeinputdigestvalue" in captured.err
    assert "accum_core.v1" in captured.err
    assert "non-authoritative" in captured.err


def test_unavailable_shadow_diagnostic_names_the_reason(
    capsys: pytest.CaptureFixture[str],
) -> None:
    shadow = ShadowBehavioralCohortIdentity(
        authoritative_compatibility_id=_VALID_COMPATIBILITY_ID,
        probe_set_id="accum_core.v1",
        projection_contract="accum_behavioral_projection.v1",
        behavioral_probe_digest=None,
        probe_input_digest=None,
        unavailable_reason="RuntimeError: probe harness exploded",
    )

    _echo_shadow_behavioral_identity(shadow)

    captured = capsys.readouterr()
    assert captured.out == "", (
        "the shadow diagnostic must never write to stdout, even in the unavailable case"
    )
    assert "unavailable" in captured.err
    assert "RuntimeError: probe harness exploded" in captured.err
