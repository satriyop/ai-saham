"""
Tests for CLI compute command.

Verifies:
- compute command for built-in indicators
- compute command for plugin indicators
- compute command for custom formulas
- Error handling

Uses Typer's CliRunner for testing.
"""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.domain.entities.candle import Candle

runner = CliRunner()


# --- Fixtures ---


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_file(temp_dir):
    """Create temporary database file path."""
    return temp_dir / "test_data.db"


@pytest.fixture
def formulas_file(temp_dir):
    """Create temporary formulas file path."""
    return temp_dir / "formulas.yaml"


@pytest.fixture
def mock_candles():
    """Create mock candles for testing."""
    from datetime import timedelta

    candles = []
    base_date = date(2024, 1, 1)
    for i in range(100):
        candles.append(
            Candle(
                ticker="BBCA",
                date=base_date + timedelta(days=i),
                open=Decimal("1000"),
                high=Decimal("1050"),
                low=Decimal("950"),
                close=Decimal(str(1000 + i)),
                volume=1000000,
            )
        )
    return candles


# --- Tests ---


class TestComputeCommand:
    """Test compute command."""

    def test_compute_unknown_indicator_shows_available(self, db_file):
        """Should show available indicators when unknown indicator is requested."""
        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "UNKNOWN_INDICATOR",
                "BBCA",
                "--db",
                str(db_file),
            ],
        )

        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "Unknown indicator" in output
        assert "Available indicators" in output
        assert "SMA" in output
        assert "EMA" in output
        assert "RSI" in output

    def test_compute_no_data_shows_fetch_hint(self, db_file):
        """Should suggest fetching data when no data is available."""
        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "RSI",
                "BBCA",
                "--db",
                str(db_file),
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 1
        output = result.output
        assert "No data for BBCA" in output or "No cached data" in output
        assert "saham fetch market BBCA --days 365" in output

    @patch("src.adapters.cli.indicator_commands.SQLiteMarketRepository")
    @patch("src.adapters.cli.indicator_commands.create_indicator_registry")
    def test_compute_builtin_indicator_success(
        self, mock_registry_fn, mock_repo_cls, mock_candles, db_file
    ):
        """Should compute built-in indicator successfully."""
        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.get_candles.return_value = mock_candles
        mock_repo_cls.return_value = mock_repo

        from datetime import timedelta
        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = True
        mock_registry.get_default_period.return_value = 14
        base = date(2024, 1, 15)
        mock_registry.compute.return_value = [
            (base + timedelta(days=i), Decimal(str(50 + i))) for i in range(40)
        ]
        mock_registry.list_indicators.return_value = ["SMA", "EMA", "RSI"]
        mock_registry_fn.return_value = mock_registry

        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "RSI",
                "BBCA",
                "--period",
                "14",
                "--tail",
                "10",
                "--db",
                str(db_file),
            ],
        )

        assert result.exit_code == 0
        assert "BBCA" in result.stdout
        assert "RSI" in result.stdout
        assert "RSI(14)" in result.stdout
        assert "Summary" in result.stdout
        assert "Latest:" in result.stdout
        mock_registry.compute.assert_called_once()

    @patch("src.adapters.cli.indicator_commands.SQLiteMarketRepository")
    @patch("src.adapters.cli.indicator_commands.create_indicator_registry")
    def test_compute_formula_hides_period(
        self, mock_registry_fn, mock_repo_cls, mock_candles, db_file
    ):
        """Should not show period for formula indicators."""
        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.get_candles.return_value = mock_candles
        mock_repo_cls.return_value = mock_repo

        from datetime import timedelta
        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = True
        mock_registry.get_default_period.return_value = 0  # Formula indicator
        base = date(2024, 1, 15)
        mock_registry.compute.return_value = [
            (base + timedelta(days=i), Decimal(str(50 + i))) for i in range(40)
        ]
        mock_registry_fn.return_value = mock_registry

        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "SMOOTH_RSI",
                "BBCA",
                "--tail",
                "10",
                "--db",
                str(db_file),
            ],
        )

        assert result.exit_code == 0
        assert "SMOOTH_RSI" in result.stdout
        # Period should not be shown for formulas (default_period=0)
        assert "Period:" not in result.stdout

    @patch("src.adapters.cli.indicator_commands.SQLiteMarketRepository")
    @patch("src.adapters.cli.indicator_commands.create_indicator_registry")
    def test_compute_insufficient_data(
        self, mock_registry_fn, mock_repo_cls, mock_candles, db_file
    ):
        """Should handle insufficient data for computation."""
        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.get_candles.return_value = mock_candles[:5]  # Only 5 candles
        mock_repo_cls.return_value = mock_repo

        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = True
        mock_registry.compute.return_value = []  # Empty result = insufficient data
        mock_registry_fn.return_value = mock_registry

        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "SMA",
                "BBCA",
                "--period",
                "50",
                "--db",
                str(db_file),
            ],
        )

        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "Insufficient data" in output

    @patch("src.adapters.cli.indicator_commands.SQLiteMarketRepository")
    @patch("src.adapters.cli.indicator_commands.create_indicator_registry")
    def test_compute_respects_tail_option(
        self, mock_registry_fn, mock_repo_cls, mock_candles, db_file
    ):
        """Should respect --tail option to limit output."""
        # Setup mocks with 100 values
        mock_repo = MagicMock()
        mock_repo.get_candles.return_value = mock_candles
        mock_repo_cls.return_value = mock_repo

        from datetime import timedelta
        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = True
        mock_registry.get_default_period.return_value = 20
        # Return 80 values
        base = date(2024, 1, 20)
        mock_registry.compute.return_value = [
            (base + timedelta(days=i), Decimal(str(100 + i))) for i in range(80)
        ]
        mock_registry_fn.return_value = mock_registry

        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "SMA",
                "BBCA",
                "--tail",
                "5",
                "--db",
                str(db_file),
            ],
        )

        assert result.exit_code == 0
        # Should show "80 (showing last 5)"
        assert "showing last 5" in result.stdout

    @patch("src.adapters.cli.indicator_commands.SQLiteMarketRepository")
    @patch("src.adapters.cli.indicator_commands.create_indicator_registry")
    def test_compute_shows_summary_statistics(
        self, mock_registry_fn, mock_repo_cls, mock_candles, db_file
    ):
        """Should show summary statistics."""
        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.get_candles.return_value = mock_candles
        mock_repo_cls.return_value = mock_repo

        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = True
        mock_registry.get_default_period.return_value = 14
        # Return values with known min/max
        mock_registry.compute.return_value = [
            (date(2024, 1, 15), Decimal("30")),  # Lowest
            (date(2024, 1, 16), Decimal("50")),
            (date(2024, 1, 17), Decimal("70")),  # Highest
            (date(2024, 1, 18), Decimal("60")),  # Latest
        ]
        mock_registry_fn.return_value = mock_registry

        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "RSI",
                "BBCA",
                "--db",
                str(db_file),
            ],
        )

        assert result.exit_code == 0
        assert "Latest:" in result.stdout
        assert "60" in result.stdout
        assert "Peak:" in result.stdout
        assert "70" in result.stdout
        assert "Trough:" in result.stdout
        assert "30" in result.stdout


class TestComputeCommandIntegration:
    """Integration tests for compute command (without mocks)."""

    def test_compute_uppercase_normalization(self, db_file):
        """Should normalize indicator name to uppercase."""
        # This test verifies the normalization happens before registry check
        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "rsi",  # lowercase
                "bbca",  # lowercase ticker
                "--db",
                str(db_file),
            ],
            catch_exceptions=False,
        )

        # Even though it fails (no data), it should be checking for RSI (uppercase)
        output = result.output
        assert "BBCA" in output  # Ticker normalized

    def test_compute_help_text(self):
        """Should show help text."""
        result = runner.invoke(app, ["indicator", "compute", "--help"])

        assert result.exit_code == 0
        assert "Compute any indicator" in result.stdout
        assert "--period" in result.stdout
        assert "--tail" in result.stdout
        assert "Examples:" in result.stdout
