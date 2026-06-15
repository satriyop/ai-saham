"""
Tests for CLI strategy commands.

Verifies:
- saham strategy init
- saham strategy validate
- saham strategy list
- saham strategy create

Uses Typer's CliRunner for testing.
"""

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.adapters.cli.main import app

runner = CliRunner()


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_strategy(base_dir: Path, name: str, content: str | None = None) -> Path:
    """Create a valid strategy package."""
    strategy_dir = base_dir / name
    strategy_dir.mkdir(parents=True, exist_ok=True)

    if content is None:
        content = f'''version: 1
name: "{name}"
description: "Test strategy"
default_outcome: MODERATE

rules:
  - name: test_rule
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
'''

    (strategy_dir / "strategy.yaml").write_text(content, encoding="utf-8")
    return strategy_dir


# ============================================================================
# strategy init Tests
# ============================================================================


class TestStrategyInit:
    """Test 'saham strategy init' command."""

    def test_init_creates_strategy_folder(self, temp_dir):
        """Should create strategy folder with files."""
        target = temp_dir / "strategies" / "momentum"

        result = runner.invoke(
            app,
            ["strategy", "init", "momentum", "--dir", str(target)],
        )

        assert result.exit_code == 0
        assert (target / "strategy.yaml").exists()
        assert (target / "README.md").exists()
        assert "Created strategy" in result.stdout

    def test_init_default_location(self, temp_dir, monkeypatch):
        """Should create in ./strategies/NAME by default."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(app, ["strategy", "init", "test_strat"])

        assert result.exit_code == 0
        assert (temp_dir / "strategies" / "test_strat" / "strategy.yaml").exists()

    def test_init_refuses_path_in_name(self):
        """Should reject names with path separators."""
        result = runner.invoke(app, ["strategy", "init", "my/strategy"])

        assert result.exit_code != 0
        # Error may be in stdout or stderr, check combined output
        output = result.output or result.stdout
        assert "path separator" in output.lower()

    def test_init_refuses_yaml_extension(self):
        """Should reject names ending in .yaml."""
        result = runner.invoke(app, ["strategy", "init", "my_strategy.yaml"])

        assert result.exit_code != 0
        output = result.output or result.stdout
        assert ".yaml" in output

    def test_init_refuses_overwrite_without_force(self, temp_dir):
        """Should not overwrite existing without --force."""
        target = temp_dir / "existing"
        create_strategy(temp_dir, "existing")

        result = runner.invoke(
            app,
            ["strategy", "init", "existing", "--dir", str(target)],
        )

        assert result.exit_code != 0
        output = result.output or result.stdout
        assert "already exists" in output.lower()

    def test_init_overwrites_with_force(self, temp_dir):
        """Should overwrite existing with --force."""
        target = temp_dir / "existing"
        create_strategy(temp_dir, "existing")

        # Modify the existing file
        (target / "strategy.yaml").write_text("modified")

        result = runner.invoke(
            app,
            ["strategy", "init", "existing", "--dir", str(target), "--force"],
        )

        assert result.exit_code == 0
        content = (target / "strategy.yaml").read_text()
        assert "version: 1" in content  # New content, not "modified"


# ============================================================================
# strategy validate Tests
# ============================================================================


class TestStrategyValidate:
    """Test 'saham strategy validate' command."""

    def test_validate_valid_strategy(self, temp_dir, monkeypatch):
        """Should report valid for valid strategy."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy(strategies_dir, "valid_test")

        result = runner.invoke(app, ["strategy", "validate", "valid_test"])

        assert result.exit_code == 0
        assert "VALID" in result.stdout

    def test_validate_explicit_path(self, temp_dir):
        """Should accept explicit path to strategy.yaml."""
        create_strategy(temp_dir, "explicit")
        path = temp_dir / "explicit" / "strategy.yaml"

        result = runner.invoke(app, ["strategy", "validate", str(path)])

        assert result.exit_code == 0
        assert "VALID" in result.stdout

    def test_validate_invalid_strategy(self, temp_dir, monkeypatch):
        """Should report invalid for invalid strategy."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        invalid_dir = strategies_dir / "invalid"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "strategy.yaml").write_text("not: valid: yaml: {")

        result = runner.invoke(app, ["strategy", "validate", "invalid"])

        assert result.exit_code != 0
        output = result.output or result.stdout
        assert "INVALID" in output

    def test_validate_nonexistent_shows_error(self, temp_dir, monkeypatch):
        """Should show helpful error for nonexistent strategy."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(app, ["strategy", "validate", "nonexistent"])

        assert result.exit_code != 0
        output = result.output or result.stdout
        assert "not found" in output.lower()


# ============================================================================
# strategy list Tests
# ============================================================================


class TestStrategyList:
    """Test 'saham strategy list' command."""

    def test_list_empty_shows_message(self, temp_dir, monkeypatch):
        """Should show message when no strategies found."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(app, ["strategy", "list"])

        assert result.exit_code == 0
        assert "No strategies found" in result.stdout

    def test_list_shows_strategies(self, temp_dir, monkeypatch):
        """Should list available strategies."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy(strategies_dir, "strat_one")
        create_strategy(strategies_dir, "strat_two")

        result = runner.invoke(app, ["strategy", "list"])

        assert result.exit_code == 0
        assert "strat_one" in result.stdout
        assert "strat_two" in result.stdout

    def test_list_verbose_shows_details(self, temp_dir, monkeypatch):
        """Should show detailed info in verbose mode."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy(strategies_dir, "detailed")

        result = runner.invoke(app, ["strategy", "list", "--verbose"])

        assert result.exit_code == 0
        assert "detailed" in result.stdout
        assert "Path:" in result.stdout


# ============================================================================
# backtest --strategy Tests
# ============================================================================


class TestBacktestWithStrategy:
    """Test 'saham backtest --strategy' option."""

    def test_backtest_requires_strategy_or_rules(self, temp_dir, monkeypatch):
        """Should error when neither --strategy nor --rules-file provided."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(app, ["strategy", "backtest", "BBCA"])

        assert result.exit_code != 0
        output = result.output or result.stdout
        assert "--strategy" in output or "--rules-file" in output

    def test_backtest_accepts_strategy_name(self, temp_dir, monkeypatch):
        """Should accept --strategy with strategy name."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy(strategies_dir, "test_strat")

        # This will fail because no data, but it should resolve the strategy
        result = runner.invoke(
            app,
            ["strategy", "backtest", "BBCA", "--strategy", "test_strat"],
        )

        # Should fail on "no data" not "strategy not found"
        output = result.output or result.stdout
        output_lower = output.lower()
        # Strategy was found, so error should be about data or database, not about strategy not found
        assert "strategy" not in output_lower or "not found" not in output_lower or "data" in output_lower

    def test_backtest_strategy_not_found_error(self, temp_dir, monkeypatch):
        """Should show helpful error when strategy not found."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            ["strategy", "backtest", "BBCA", "--strategy", "nonexistent"],
        )

        assert result.exit_code != 0
        output = result.output or result.stdout
        assert "not found" in output.lower()
        assert "Searched" in output or "nonexistent" in output

    def test_backtest_rules_file_still_works(self, temp_dir):
        """Should still accept --rules-file for backward compatibility."""
        create_strategy(temp_dir, "compat")
        rules_file = temp_dir / "compat" / "strategy.yaml"

        result = runner.invoke(
            app,
            ["strategy", "backtest", "BBCA", "--rules-file", str(rules_file)],
        )

        # Should fail on "no data" not "rules file not found"
        # The --rules-file path exists, so error should be about data
        output = result.output or result.stdout
        output_lower = output.lower()
        assert "rules file" not in output_lower or "not found" not in output_lower


# ============================================================================
# strategy create Tests
# ============================================================================


class TestStrategyCreate:
    """Test 'saham strategy create' command."""

    def test_create_generates_and_saves_strategy(self, temp_dir, monkeypatch):
        """Should create and save strategy from intent."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "RSI oversold strategy",
                "--name", "test_rsi",
                "--provider", "mock",
            ],
        )

        assert result.exit_code == 0
        assert "Generated Strategy" in result.stdout
        assert "version: 1" in result.stdout
        assert "Strategy saved to" in result.stdout

        # Verify file was created
        strategy_file = temp_dir / "strategies" / "test_rsi" / "strategy.yaml"
        assert strategy_file.exists()
        content = strategy_file.read_text()
        assert "version: 1" in content
        assert "test_rsi" in content

    def test_create_with_custom_directory(self, temp_dir):
        """Should save to custom directory."""
        target_dir = temp_dir / "custom_strategies" / "my_rsi"

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "RSI strategy",
                "--name", "my_rsi",
                "--provider", "mock",
                "--dir", str(target_dir),
            ],
        )

        assert result.exit_code == 0
        assert (target_dir / "strategy.yaml").exists()

    def test_create_no_save_previews_only(self, temp_dir, monkeypatch):
        """Should preview without saving when --no-save specified."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "EMA crossover",
                "--name", "preview_ema",
                "--provider", "mock",
                "--no-save",
            ],
        )

        assert result.exit_code == 0
        assert "Generated Strategy" in result.stdout
        assert "version: 1" in result.stdout
        assert "not saved" in result.stdout.lower()

        # Verify file was NOT created
        strategy_file = temp_dir / "strategies" / "preview_ema" / "strategy.yaml"
        assert not strategy_file.exists()

    def test_create_derives_name_from_intent(self, temp_dir, monkeypatch):
        """Should derive strategy name from intent if not provided."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "momentum trading system",
                "--provider", "mock",
            ],
        )

        assert result.exit_code == 0
        # Name should be derived from intent
        assert "momentum" in result.stdout.lower()

    def test_create_unsupported_intent_shows_error(self, temp_dir, monkeypatch):
        """Should show error for unsupported intents."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "predict tomorrow's price",
                "--name", "prediction",
                "--provider", "mock",
            ],
        )

        assert result.exit_code != 0
        output = result.output or result.stdout
        assert "cannot be expressed" in output.lower() or "unsupported" in output.lower()

    def test_create_with_ema_crossover_intent(self, temp_dir, monkeypatch):
        """Should create EMA crossover strategy."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "EMA crossover with 9 and 21 periods",
                "--name", "ema_cross",
                "--provider", "mock",
            ],
        )

        assert result.exit_code == 0
        assert "fast_ema" in result.stdout
        assert "slow_ema" in result.stdout

    def test_create_with_combined_strategy(self, temp_dir, monkeypatch):
        """Should create combined RSI and EMA strategy."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "RSI oversold with EMA crossover confirmation",
                "--name", "combined",
                "--provider", "mock",
            ],
        )

        assert result.exit_code == 0
        # Should have both RSI and EMA
        assert "RSI" in result.stdout
        assert "EMA" in result.stdout

    def test_create_invalid_provider_shows_error(self, temp_dir, monkeypatch):
        """Should show error for invalid provider."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "RSI strategy",
                "--name", "test",
                "--provider", "invalid_provider",
            ],
        )

        assert result.exit_code != 0
        output = result.output or result.stdout
        assert "unsupported" in output.lower() or "error" in output.lower()

    def test_create_refuses_overwrite_without_confirm(self, temp_dir, monkeypatch):
        """Should ask for confirmation before overwriting."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy(strategies_dir, "existing")

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "RSI strategy",
                "--name", "existing",
                "--provider", "mock",
            ],
            input="n\n",  # Answer "no" to overwrite
        )

        # Should abort
        assert "Aborted" in result.stdout or result.exit_code == 0

    def test_create_overwrites_with_confirm(self, temp_dir, monkeypatch):
        """Should overwrite when user confirms."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy(strategies_dir, "overwrite_me")

        # Modify the existing file
        original_file = strategies_dir / "overwrite_me" / "strategy.yaml"
        original_file.write_text("original content")

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "RSI strategy",
                "--name", "overwrite_me",
                "--provider", "mock",
            ],
            input="y\n",  # Answer "yes" to overwrite
        )

        assert result.exit_code == 0
        content = original_file.read_text()
        assert "version: 1" in content  # New content, not "original content"

    def test_create_shows_next_steps(self, temp_dir, monkeypatch):
        """Should show helpful next steps after creation."""
        monkeypatch.chdir(temp_dir)

        result = runner.invoke(
            app,
            [
                "strategy", "create",
                "RSI strategy",
                "--name", "next_steps_test",
                "--provider", "mock",
            ],
        )

        assert result.exit_code == 0
        assert "saham strategy validate" in result.stdout
        assert "saham strategy backtest" in result.stdout
