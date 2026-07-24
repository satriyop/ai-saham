"""Composition root for stock-axis view ticker deps."""

from pathlib import Path

from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps


def test_build_view_ticker_deps_exposes_all_use_cases(tmp_path: Path):
    deps = build_view_ticker_deps(tmp_path / "data.db")
    assert deps.db_path.name == "data.db"
    assert deps.dashboard is not None
    assert deps.top_brokers is not None
    assert deps.flow is not None
    assert deps.foreign_history is not None
    assert deps.distribution is not None
    assert deps.broker_repository is not None
