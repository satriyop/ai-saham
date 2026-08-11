"""Market context / regime CLI command tests."""

import sqlite3
from pathlib import Path

from src.adapters.cli.main import app
from tests.adapters.cli.plan_swing_command_fixtures import runner


def test_regime_command_accepts_explicit_ticker_with_empty_cache(tmp_path: Path):
    # Explicit --db is fail-closed and never creates a database (CLI_REFERENCE
    # "Exit codes"; b555bb88). An empty SQLite file is also a truer fixture for
    # "empty cache" than a path that does not exist at all.
    sqlite3.connect(tmp_path / "empty.db").close()

    result = runner.invoke(
        app,
        [
            "inspect",
            "regime",
            "BBCA",
            "--universe",
            "cached",
            "--db",
            str(tmp_path / "empty.db"),
            "--as-of",
            "2026-06-12",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Market Context" in result.output
