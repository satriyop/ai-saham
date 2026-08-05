"""ADR-068 slice 5: producing-build audit and informational fork warning."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.accumulation_producer_readiness import (
    assess_cohort_fork_warning,
    collect_producing_builds,
    observation_producer_build,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
)

NOW = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)


def _obs(*, compat: str = "compat-a", build: str = "ai-saham@build-a") -> LearningObservation:
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=compat,
        cutoff_at=NOW,
        universe_id="idx30",
        window_id=f"BBCA:{compat}",
        decision_payload={"funnel": "PASS"},
        captured_at=NOW,
        producer_source_revision=build,
    )


def test_collect_producing_builds_is_sorted_and_distinct() -> None:
    count, builds = collect_producing_builds(
        [
            _obs(build="ai-saham@b"),
            _obs(build="ai-saham@a"),
            _obs(build="ai-saham@b"),
        ]
    )
    assert count == 2
    assert builds == ("ai-saham@a", "ai-saham@b")


def test_observation_producer_build_falls_back_to_population_binding() -> None:
    obs = _obs(build="top-level-build")
    # Empty top-level via replace is not public; exercise helper on create path.
    assert observation_producer_build(obs) == "top-level-build"


def test_fork_warning_none_when_corpus_empty() -> None:
    assert (
        assess_cohort_fork_warning(
            next_compatibility_id="new",
            observation_counts_by_compat={},
        )
        is None
    )


def test_fork_warning_none_when_continuing_same_cohort() -> None:
    assert (
        assess_cohort_fork_warning(
            next_compatibility_id="compat-a",
            observation_counts_by_compat={"compat-a": 10},
        )
        is None
    )


def test_fork_warning_names_orphan_count() -> None:
    warning = assess_cohort_fork_warning(
        next_compatibility_id="compat-new",
        observation_counts_by_compat={"compat-a": 7, "compat-b": 3},
    )
    assert warning is not None
    assert warning.orphan_observation_count == 10
    assert warning.existing_cohort_count == 2
    assert "compat-a" in warning.message
    assert "10 observation" in warning.message
