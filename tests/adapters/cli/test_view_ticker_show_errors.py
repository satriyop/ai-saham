"""High-traffic view ticker show error honesty (task 08 MVP)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from src.adapters.cli import view_ticker_show_commands as show_mod


def test_invalid_format_exits_user(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        show_mod,
        "load_app_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(db_path=str(tmp_path / "d.db"))),
    )
    db = tmp_path / "d.db"
    db.write_bytes(b"")
    with pytest.raises(typer.Exit) as ei:
        show_mod.ticker_show(ticker="BBCA", output_format="yaml", db_path=db)
    assert ei.value.exit_code == 1


def test_missing_explicit_db_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        show_mod,
        "load_app_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(db_path=str(tmp_path / "d.db"))),
    )
    missing = tmp_path / "no" / "x.db"
    with pytest.raises(typer.Exit) as ei:
        show_mod.ticker_show(ticker="BBCA", db_path=missing)
    assert ei.value.exit_code == 1
    assert not missing.exists()


def test_empty_cache_exits_data_unavailable(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    db.write_bytes(b"")
    monkeypatch.setattr(
        show_mod,
        "load_app_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(db_path=str(db))),
    )

    empty_dashboard = SimpleNamespace(
        candles=(),
        notation=None,
        latest_close=None,
        profile=None,
        bandar=None,
        foreign_flow_points=(),
        price_structure=None,
        fetch_hint="saham fetch market ZZZZ --days 365",
    )
    fake_uc = SimpleNamespace(execute=lambda req: empty_dashboard)
    monkeypatch.setattr(
        "src.infrastructure.composition.view_ticker_deps.build_view_ticker_deps",
        lambda path: SimpleNamespace(dashboard=fake_uc),
    )

    with pytest.raises(typer.Exit) as ei:
        show_mod.ticker_show(ticker="ZZZZ", db_path=db)
    assert ei.value.exit_code == 2
