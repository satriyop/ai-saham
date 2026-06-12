"""Tests for update command helper behavior."""

from pathlib import Path

from src.adapters.cli.update_commands import _fetch_broker


def test_fetch_broker_skips_index_ticker(tmp_path: Path):
    status = _fetch_broker(
        ticker="^JKSE",
        days=90,
        db_path=tmp_path / "data.db",
        broker_provider=object(),
        refresh=False,
    )

    assert status == "n/a:index"
