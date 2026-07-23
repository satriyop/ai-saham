"""Tests for MCE observation identity / config cohort hashing."""

from __future__ import annotations

from src.application.services.mce_observation_identity import (
    MARKET_CONTEXT_REGIME_CONTRACT,
    build_mce_observation_identity,
    resolve_mce_semantic_compatibility_id,
)

_SAMPLE_YAML = """
market_context_engine:
  scoring:
    neutral_score: 0.5
"""


def test_same_inputs_produce_same_semantic_compatibility_id():
    id_a = resolve_mce_semantic_compatibility_id(
        resolved_mce_config_canonical=_SAMPLE_YAML,
        universe_name="lq45",
        benchmark_ticker="IHSG",
    )
    id_b = resolve_mce_semantic_compatibility_id(
        resolved_mce_config_canonical=_SAMPLE_YAML,
        universe_name="lq45",
        benchmark_ticker="IHSG",
    )
    assert id_a == id_b


def test_yaml_change_forks_cohort_id():
    base = resolve_mce_semantic_compatibility_id(
        resolved_mce_config_canonical=_SAMPLE_YAML,
        universe_name="lq45",
        benchmark_ticker="IHSG",
    )
    changed = resolve_mce_semantic_compatibility_id(
        resolved_mce_config_canonical=_SAMPLE_YAML + "\n# tuned",
        universe_name="lq45",
        benchmark_ticker="IHSG",
    )
    assert base != changed


def test_universe_change_forks_cohort_id():
    lq45 = resolve_mce_semantic_compatibility_id(
        resolved_mce_config_canonical=_SAMPLE_YAML,
        universe_name="lq45",
        benchmark_ticker="IHSG",
    )
    idx80 = resolve_mce_semantic_compatibility_id(
        resolved_mce_config_canonical=_SAMPLE_YAML,
        universe_name="idx80",
        benchmark_ticker="IHSG",
    )
    assert lq45 != idx80


def test_build_mce_observation_identity_sets_contract_and_normalized_context():
    identity = build_mce_observation_identity(
        resolved_mce_config_canonical=_SAMPLE_YAML,
        universe_name=" LQ45 ",
        benchmark_ticker=" ihsg ",
    )
    assert identity.observation_contract == MARKET_CONTEXT_REGIME_CONTRACT
    assert identity.universe_name == "lq45"
    assert identity.benchmark_ticker == "IHSG"
    assert identity.cohort_id.startswith("sha256:")
