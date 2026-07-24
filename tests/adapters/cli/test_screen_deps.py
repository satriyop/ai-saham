"""Composition root for screen discovery deps."""

from pathlib import Path

from src.adapters.cli.screen_deps import build_screen_deps


def test_build_screen_deps_exposes_watchlist_and_accum_builders(tmp_path: Path):
    deps = build_screen_deps(tmp_path / "data.db")
    assert deps.db_path.name == "data.db"
    assert deps.list_watchlists is not None
    assert deps.save_watchlist is not None
    assert deps.broker_repository is not None
    assert deps.market_repository is not None
    assert callable(deps.build_accum_workflow_use_case)
    assert callable(deps.build_compare_watchlist_use_case)
