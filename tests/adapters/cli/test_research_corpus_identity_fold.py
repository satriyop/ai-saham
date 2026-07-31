"""N (pit_tradable_lookback_sessions) must fold into lean identity canonical string."""

from __future__ import annotations

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
