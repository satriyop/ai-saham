"""N (pit_tradable_lookback_sessions) must fold into lean identity canonical string."""

from __future__ import annotations

from dataclasses import replace

from src.adapters.cli.research_accum_backfill_commands import _read_scoring_config_canonical
from src.application.services.lean_observation_identity import (
    resolve_lean_semantic_compatibility_id,
)
from src.infrastructure.config.app_config import load_app_config


def test_changing_pit_window_n_forks_semantic_compatibility_id() -> None:
    cfg = load_app_config()
    base = _read_scoring_config_canonical(
        cfg.config_paths,
        pit_tradable_lookback_sessions=10,
    )
    changed = _read_scoring_config_canonical(
        cfg.config_paths,
        pit_tradable_lookback_sessions=11,
    )
    assert base != changed
    assert resolve_lean_semantic_compatibility_id(base) != resolve_lean_semantic_compatibility_id(
        changed
    )
    assert "# pit_tradable_lookback_sessions\n10" in base
    assert "# pit_tradable_lookback_sessions\n11" in changed


def test_risk_engine_is_material_to_corpus_compatibility(tmp_path) -> None:
    cfg = load_app_config()
    risk_a = tmp_path / "risk-a.yaml"
    risk_b = tmp_path / "risk-b.yaml"
    risk_a.write_text("risk_engine:\n  gates:\n    fundamental:\n      piotroski_min: 3\n")
    risk_b.write_text("risk_engine:\n  gates:\n    fundamental:\n      piotroski_min: 4\n")

    paths_a = replace(cfg.config_paths, risk_engine=str(risk_a))
    paths_b = replace(cfg.config_paths, risk_engine=str(risk_b))
    canonical_a = _read_scoring_config_canonical(paths_a, pit_tradable_lookback_sessions=10)
    canonical_b = _read_scoring_config_canonical(paths_b, pit_tradable_lookback_sessions=10)

    assert canonical_a != canonical_b
    assert resolve_lean_semantic_compatibility_id(
        canonical_a
    ) != resolve_lean_semantic_compatibility_id(canonical_b)
