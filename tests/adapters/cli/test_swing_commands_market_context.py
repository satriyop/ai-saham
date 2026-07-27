"""Market context / regime CLI command tests."""

from pathlib import Path

from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import runner


def test_regime_command_accepts_explicit_ticker_with_empty_cache(tmp_path: Path):
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
