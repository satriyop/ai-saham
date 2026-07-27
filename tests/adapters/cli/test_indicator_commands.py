"""
Tests for CLI indicator commands.

Verifies:
- create-indicator command
- list-indicators command
- show-formula command
- delete-indicator command

Uses Typer's CliRunner for testing.
"""

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.infrastructure.persistence.formula_storage import FormulaStorage

runner = CliRunner()


# --- Fixtures ---


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def formulas_file(temp_dir):
    """Create temporary formulas file path."""
    return temp_dir / "formulas.yaml"


@pytest.fixture
def storage(formulas_file):
    """Create storage with temp path."""
    return FormulaStorage(path=formulas_file)


# --- Tests ---


class TestCreateIndicator:
    """Test create-indicator command."""

    def test_creates_indicator_with_mock_provider(self, formulas_file):
        """Should create indicator using mock provider."""
        result = runner.invoke(
            app,
            [
                "indicator",
                "create",
                "smoothed RSI with 14 period",
                "--name",
                "SMOOTH_RSI",
                "--provider",
                "mock",
                "--formulas",
                str(formulas_file),
            ],
        )

        assert result.exit_code == 0
        assert "SMA(RSI(14), 10)" in result.stdout
        assert "SMOOTH_RSI" in result.stdout

    def test_saves_formula_to_storage(self, formulas_file, storage):
        """Should save formula to storage."""
        runner.invoke(
            app,
            [
                "indicator",
                "create",
                "14-day RSI",
                "--name",
                "MY_RSI",
                "--provider",
                "mock",
                "--formulas",
                str(formulas_file),
            ],
        )

        stored = storage.get("MY_RSI")

        assert stored is not None
        assert stored.formula == "RSI(14)"

    def test_no_save_flag_skips_storage(self, formulas_file, storage):
        """Should not save when --no-save is used."""
        runner.invoke(
            app,
            [
                "indicator",
                "create",
                "14-day RSI",
                "--name",
                "MY_RSI",
                "--provider",
                "mock",
                "--no-save",
                "--formulas",
                str(formulas_file),
            ],
        )

        assert not storage.exists("MY_RSI")

    def test_auto_generates_name_when_not_provided(self, formulas_file):
        """Should auto-generate name when not provided."""
        result = runner.invoke(
            app,
            [
                "indicator",
                "create",
                "simple moving average",
                "--provider",
                "mock",
                "--formulas",
                str(formulas_file),
            ],
        )

        assert result.exit_code == 0
        assert "Auto-generated name:" in result.stdout

    def test_handles_unsupported_intent(self, formulas_file):
        """Should handle unsupported intent gracefully."""
        result = runner.invoke(
            app,
            [
                "indicator",
                "create",
                "predict tomorrow price",  # mock returns UNSUPPORTED
                "--provider",
                "mock",
                "--formulas",
                str(formulas_file),
            ],
        )

        assert result.exit_code == 1
        # Error messages may go to stderr
        output = result.stdout + (result.stderr or "")
        assert "cannot be expressed" in output


class TestListIndicators:
    """Test list-indicators command."""

    def test_lists_builtin_indicators(self):
        """Should list built-in indicators."""
        result = runner.invoke(app, ["indicator", "list"])

        assert result.exit_code == 0
        assert "SMA" in result.stdout
        assert "EMA" in result.stdout
        assert "RSI" in result.stdout

    def test_shows_custom_formulas(self, formulas_file, storage):
        """Should show custom formulas."""
        storage.save("MY_INDICATOR", "SMA(RSI(14), 10)")

        result = runner.invoke(
            app,
            ["indicator", "list", "--formulas-file", str(formulas_file)],
        )

        assert result.exit_code == 0
        assert "MY_INDICATOR" in result.stdout

    def test_shows_formula_expressions_with_flag(self, formulas_file, storage):
        """Should show formula expressions with --formulas flag."""
        storage.save("MY_INDICATOR", "SMA(RSI(14), 10)")

        result = runner.invoke(
            app,
            ["indicator", "list", "--formulas", "--formulas-file", str(formulas_file)],
        )

        assert result.exit_code == 0
        assert "SMA(RSI(14), 10)" in result.stdout


class TestShowFormula:
    """Test show-formula command."""

    def test_shows_formula_details(self, formulas_file, storage):
        """Should show formula details."""
        storage.save("MY_RSI", "RSI(14)", intent="14-day RSI")

        result = runner.invoke(
            app,
            ["indicator", "show", "MY_RSI", "--formulas-file", str(formulas_file)],
        )

        assert result.exit_code == 0
        assert "MY_RSI" in result.stdout
        assert "RSI(14)" in result.stdout
        assert "14-day RSI" in result.stdout

    def test_handles_not_found(self, formulas_file):
        """Should handle non-existent formula."""
        result = runner.invoke(
            app,
            ["indicator", "show", "NONEXISTENT", "--formulas-file", str(formulas_file)],
        )

        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "not found" in output

    def test_case_insensitive(self, formulas_file, storage):
        """Should be case-insensitive."""
        storage.save("MY_RSI", "RSI(14)")

        result = runner.invoke(
            app,
            ["indicator", "show", "my_rsi", "--formulas-file", str(formulas_file)],
        )

        assert result.exit_code == 0
        assert "MY_RSI" in result.stdout


class TestDeleteIndicator:
    """Test delete-indicator command."""

    def test_deletes_formula_with_force(self, formulas_file, storage):
        """Should delete formula with --force flag."""
        storage.save("MY_RSI", "RSI(14)")

        result = runner.invoke(
            app,
            ["indicator", "delete", "MY_RSI", "--force", "--formulas-file", str(formulas_file)],
        )

        assert result.exit_code == 0
        assert "Deleted" in result.stdout
        assert not storage.exists("MY_RSI")

    def test_handles_not_found(self, formulas_file):
        """Should handle non-existent formula."""
        result = runner.invoke(
            app,
            [
                "indicator",
                "delete",
                "NONEXISTENT",
                "--force",
                "--formulas-file",
                str(formulas_file),
            ],
        )

        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "not found" in output

    def test_rejects_builtin_indicator(self, formulas_file):
        """Should reject deletion of built-in indicator."""
        result = runner.invoke(
            app,
            ["indicator", "delete", "SMA", "--force", "--formulas-file", str(formulas_file)],
        )

        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "built-in" in output

    def test_prompts_for_confirmation(self, formulas_file, storage):
        """Should prompt for confirmation without --force."""
        storage.save("MY_RSI", "RSI(14)")

        result = runner.invoke(
            app,
            ["indicator", "delete", "MY_RSI", "--formulas-file", str(formulas_file)],
            input="n\n",  # Decline confirmation
        )

        assert "Delete this formula?" in result.stdout
        assert storage.exists("MY_RSI")  # Not deleted

    def test_deletes_on_confirmation(self, formulas_file, storage):
        """Should delete on confirmation."""
        storage.save("MY_RSI", "RSI(14)")

        result = runner.invoke(
            app,
            ["indicator", "delete", "MY_RSI", "--formulas-file", str(formulas_file)],
            input="y\n",  # Confirm
        )

        assert result.exit_code == 0
        assert not storage.exists("MY_RSI")
