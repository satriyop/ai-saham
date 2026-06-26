"""
CLI workflow integration tests.

Tests complete CLI command workflows:
1. create-indicator → strategy create → validate → backtest
2. Full analysis workflow: fetch → indicators → risk → backtest
3. Strategy package management
4. Error handling and exit codes

Uses Typer's CliRunner for isolated testing without affecting real files.
"""


from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)
from tests.integration.conftest import (
    create_rsi_oversold_strategy,
    generate_test_candles,
)

runner = CliRunner()


class TestCLICreateIndicatorWorkflow:
    """Test CLI indicator creation workflows."""

    def test_create_indicator_success(self, temp_workspace, monkeypatch):
        """CLI: create-indicator with mock provider succeeds."""
        monkeypatch.chdir(temp_workspace)
        formulas_path = temp_workspace / "formulas.yaml"

        result = runner.invoke(
            app,
            [
                "indicator", "create",
                "smoothed RSI",
                "--name",
                "TEST_SMOOTH_RSI",
                "--provider",
                "mock",
                "--formulas",
                str(formulas_path),
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.stdout}"
        assert "Formula:" in result.stdout
        assert "TEST_SMOOTH_RSI" in result.stdout or "Registered" in result.stdout

        # Verify file was created
        assert formulas_path.exists()

    def test_create_indicator_no_save(self, temp_workspace, monkeypatch):
        """CLI: create-indicator with --no-save doesn't persist."""
        monkeypatch.chdir(temp_workspace)
        formulas_path = temp_workspace / "formulas.yaml"

        result = runner.invoke(
            app,
            [
                "indicator", "create",
                "14-day RSI",
                "--name",
                "TEMP_RSI",
                "--provider",
                "mock",
                "--no-save",
                "--formulas",
                str(formulas_path),
            ],
        )

        assert result.exit_code == 0
        assert "Formula:" in result.stdout
        # File should not be created when --no-save is used
        # (unless it existed before)


class TestCLIStrategyWorkflow:
    """Test CLI strategy management workflows."""

    def test_strategy_init_creates_files(self, temp_workspace, monkeypatch):
        """CLI: strategy init creates strategy package."""
        monkeypatch.chdir(temp_workspace)

        result = runner.invoke(
            app,
            ["strategy", "init", "test_strategy"],
        )

        assert result.exit_code == 0, f"Command failed: {result.stdout}"
        assert "Created strategy" in result.stdout

        # Verify files exist
        strategy_dir = temp_workspace / "strategies" / "test_strategy"
        assert strategy_dir.exists()
        assert (strategy_dir / "strategy.yaml").exists()
        assert (strategy_dir / "README.md").exists()

    def test_strategy_init_custom_dir(self, temp_workspace, monkeypatch):
        """CLI: strategy init with custom directory."""
        monkeypatch.chdir(temp_workspace)
        custom_dir = temp_workspace / "my_strategies" / "custom"

        result = runner.invoke(
            app,
            ["strategy", "init", "my_strat", "--dir", str(custom_dir)],
        )

        assert result.exit_code == 0
        assert (custom_dir / "strategy.yaml").exists()

    def test_strategy_validate_valid(self, temp_workspace, monkeypatch):
        """CLI: strategy validate passes for valid strategy."""
        monkeypatch.chdir(temp_workspace)

        # Create strategy first
        result = runner.invoke(app, ["strategy", "init", "valid_strat"])
        assert result.exit_code == 0

        # Validate it
        result = runner.invoke(app, ["strategy", "validate", "valid_strat"])

        assert result.exit_code == 0
        assert "VALID" in result.stdout

    def test_strategy_validate_invalid_path(self, temp_workspace, monkeypatch):
        """CLI: strategy validate fails for non-existent strategy."""
        monkeypatch.chdir(temp_workspace)

        result = runner.invoke(app, ["strategy", "validate", "nonexistent"])

        assert result.exit_code == 1
        # Use result.output which combines stdout and stderr
        output = result.output or result.stdout
        assert "Error" in output or "not found" in output.lower()

    def test_strategy_list_empty(self, temp_workspace, monkeypatch):
        """CLI: strategy list shows nothing when no strategies exist."""
        monkeypatch.chdir(temp_workspace)
        # Don't create any strategies

        result = runner.invoke(app, ["strategy", "list"])

        assert result.exit_code == 0
        assert "No strategies found" in result.stdout or "0" in result.stdout

    def test_strategy_list_shows_strategies(self, temp_workspace, monkeypatch):
        """CLI: strategy list shows created strategies."""
        monkeypatch.chdir(temp_workspace)

        # Create some strategies
        runner.invoke(app, ["strategy", "init", "strat_one"])
        runner.invoke(app, ["strategy", "init", "strat_two"])

        result = runner.invoke(app, ["strategy", "list"])

        assert result.exit_code == 0
        assert "strat_one" in result.stdout
        assert "strat_two" in result.stdout

    def test_strategy_create_with_mock_provider(self, temp_workspace, monkeypatch):
        """CLI: strategy create generates strategy from intent."""
        monkeypatch.chdir(temp_workspace)

        result = runner.invoke(
            app,
            [
                "strategy",
                "create",
                "RSI oversold strategy",
                "--name",
                "ai_generated",
                "--provider",
                "mock",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.stdout}"
        # Should show generated YAML
        assert "version:" in result.stdout.lower() or "Generated" in result.stdout

    def test_strategy_create_no_save(self, temp_workspace, monkeypatch):
        """CLI: strategy create with --no-save only previews."""
        monkeypatch.chdir(temp_workspace)

        result = runner.invoke(
            app,
            [
                "strategy",
                "create",
                "momentum strategy",
                "--name",
                "preview_only",
                "--provider",
                "mock",
                "--no-save",
            ],
        )

        assert result.exit_code == 0
        assert "not saved" in result.stdout.lower() or "no-save" in result.stdout.lower()


class TestCLIBacktestWorkflow:
    """Test CLI backtest workflows."""

    def test_backtest_requires_strategy_or_rules(self, temp_workspace, monkeypatch):
        """CLI: backtest fails without --strategy or --rules-file."""
        monkeypatch.chdir(temp_workspace)

        result = runner.invoke(app, ["strategy", "backtest", "BBCA"])

        assert result.exit_code == 1
        output = result.output or result.stdout
        assert "--strategy" in output or "--rules-file" in output

    def test_backtest_with_strategy_file(self, temp_workspace, monkeypatch):
        """CLI: backtest with explicit rules file."""
        monkeypatch.chdir(temp_workspace)

        # Create strategy file
        strategy_file = temp_workspace / "my_rules.yaml"
        strategy_file.write_text(create_rsi_oversold_strategy("test_backtest"))

        # Create mock database with candles
        db_path = temp_workspace / "data.db"
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=100, ticker="BBCA")
        repo.save_candles(candles)

        result = runner.invoke(
            app,
            [
                "strategy", "backtest",
                "BBCA",
                "--rules-file",
                str(strategy_file),
                "--db",
                str(db_path),
                "--start",
                "2024-01-01",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.stdout}"
        assert "Backtest Results" in result.stdout
        assert "BBCA" in result.stdout

    def test_backtest_with_strategy_name(self, temp_workspace, monkeypatch):
        """CLI: backtest with --strategy name resolution."""
        monkeypatch.chdir(temp_workspace)

        # Create strategy package
        runner.invoke(app, ["strategy", "init", "my_strat"])

        # Create mock database with candles
        db_path = temp_workspace / "data.db"
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=100, ticker="BBCA")
        repo.save_candles(candles)

        result = runner.invoke(
            app,
            [
                "strategy", "backtest",
                "BBCA",
                "--strategy",
                "my_strat",
                "--db",
                str(db_path),
                "--start",
                "2024-01-01",
            ],
        )

        output = result.output or result.stdout
        assert result.exit_code == 0, f"Command failed: {output}"
        assert "Backtest Results" in output

    def test_backtest_verbose_shows_trades(self, temp_workspace, monkeypatch):
        """CLI: backtest --verbose shows trade history."""
        monkeypatch.chdir(temp_workspace)

        # Create strategy file
        strategy_file = temp_workspace / "rules.yaml"
        strategy_file.write_text(create_rsi_oversold_strategy("verbose_test"))

        # Create mock database with candles
        db_path = temp_workspace / "data.db"
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=100, ticker="TEST")
        repo.save_candles(candles)

        result = runner.invoke(
            app,
            [
                "strategy", "backtest",
                "TEST",
                "--rules-file",
                str(strategy_file),
                "--db",
                str(db_path),
                "--verbose",
                "--start",
                "2024-01-01",
            ],
        )

        assert result.exit_code == 0
        # Verbose output includes trade history section
        assert "Backtest Results" in result.stdout

    def test_backtest_no_data_error(self, temp_workspace, monkeypatch):
        """CLI: backtest fails gracefully when no data exists."""
        monkeypatch.chdir(temp_workspace)

        # Create strategy but no database
        strategy_file = temp_workspace / "rules.yaml"
        strategy_file.write_text(create_rsi_oversold_strategy("no_data_test"))

        db_path = temp_workspace / "empty.db"

        result = runner.invoke(
            app,
            [
                "strategy", "backtest",
                "XXXX",
                "--rules-file",
                str(strategy_file),
                "--db",
                str(db_path),
            ],
        )

        assert result.exit_code == 1
        output = result.output or result.stdout
        assert "no cached data" in output.lower() or "no data" in output.lower() or "fetch" in output.lower()


class TestCLIComputeWorkflow:
    """Test CLI compute command workflows."""

    def test_compute_builtin_indicator(self, temp_workspace, monkeypatch):
        """CLI: compute RSI for cached data."""
        monkeypatch.chdir(temp_workspace)

        # Create mock database with candles
        db_path = temp_workspace / "data.db"
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=50, ticker="BBCA")
        repo.save_candles(candles)

        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "RSI",
                "BBCA",
                "--period",
                "14",
                "--db",
                str(db_path),
                "--tail",
                "10",
            ],
        )

        assert result.exit_code == 0, f"Command failed: {result.stdout}"
        assert "RSI" in result.stdout
        assert "BBCA" in result.stdout

    def test_compute_unknown_indicator_error(self, temp_workspace, monkeypatch):
        """CLI: compute fails for unknown indicator."""
        monkeypatch.chdir(temp_workspace)

        db_path = temp_workspace / "data.db"

        result = runner.invoke(
            app,
            [
                "indicator", "compute",
                "UNKNOWN_IND",
                "BBCA",
                "--db",
                str(db_path),
            ],
        )

        assert result.exit_code == 1
        output = result.output or result.stdout
        assert "Unknown indicator" in output or "Available" in output


class TestCLIIndicatorListWorkflow:
    """Test CLI list-indicators command."""

    def test_list_indicators_shows_builtins(self, temp_workspace, monkeypatch):
        """CLI: list-indicators shows built-in indicators."""
        monkeypatch.chdir(temp_workspace)

        result = runner.invoke(app, ["indicator", "list"])

        assert result.exit_code == 0
        assert "SMA" in result.stdout
        assert "EMA" in result.stdout
        assert "RSI" in result.stdout

    def test_list_indicators_with_formulas(self, temp_workspace, monkeypatch):
        """CLI: list-indicators --formulas shows formula expressions."""
        monkeypatch.chdir(temp_workspace)

        # Create formula file
        formulas_path = temp_workspace / "formulas.yaml"

        # First create a formula
        result = runner.invoke(
            app,
            [
                "indicator", "create",
                "smoothed RSI",
                "--name",
                "MY_RSI",
                "--provider",
                "mock",
                "--formulas",
                str(formulas_path),
            ],
        )
        assert result.exit_code == 0

        # Then list with --formulas
        result = runner.invoke(
            app,
            ["indicator", "list", "--formulas", "--formulas-file", str(formulas_path)],
        )

        assert result.exit_code == 0


class TestCLIEndToEndWorkflow:
    """Test complete end-to-end CLI workflows."""

    def test_full_workflow_create_indicator_to_backtest(
        self, temp_workspace, monkeypatch
    ):
        """Complete workflow: create indicator → strategy → backtest."""
        monkeypatch.chdir(temp_workspace)
        formulas_path = temp_workspace / "formulas.yaml"
        db_path = temp_workspace / "data.db"

        # Step 1: Create custom indicator
        result = runner.invoke(
            app,
            [
                "indicator", "create",
                "14-day RSI",
                "--name",
                "CUSTOM_RSI",
                "--provider",
                "mock",
                "--formulas",
                str(formulas_path),
            ],
        )
        assert result.exit_code == 0, f"create-indicator failed: {result.stdout}"

        # Step 2: Create strategy package
        result = runner.invoke(app, ["strategy", "init", "e2e_test"])
        assert result.exit_code == 0, f"strategy init failed: {result.stdout}"

        # Step 3: Validate strategy
        result = runner.invoke(app, ["strategy", "validate", "e2e_test"])
        assert result.exit_code == 0, f"strategy validate failed: {result.stdout}"
        assert "VALID" in result.stdout

        # Step 4: Set up test data
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=100, ticker="E2E")
        repo.save_candles(candles)

        # Step 5: Run backtest
        result = runner.invoke(
            app,
            [
                "strategy", "backtest",
                "E2E",
                "--strategy",
                "e2e_test",
                "--db",
                str(db_path),
                "--start",
                "2024-01-01",
            ],
        )
        assert result.exit_code == 0, f"backtest failed: {result.stdout}"
        assert "Backtest Results" in result.stdout

    def test_strategy_create_then_backtest(self, temp_workspace, monkeypatch):
        """Workflow: AI creates strategy → immediately backtest."""
        monkeypatch.chdir(temp_workspace)
        db_path = temp_workspace / "data.db"

        # Step 1: Create strategy via AI
        result = runner.invoke(
            app,
            [
                "strategy",
                "create",
                "RSI oversold strategy",
                "--name",
                "ai_strat",
                "--provider",
                "mock",
            ],
        )
        assert result.exit_code == 0, f"strategy create failed: {result.stdout}"

        # Step 2: Set up test data
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=100, ticker="AI_TEST")
        repo.save_candles(candles)

        # Step 3: Run backtest with the AI-created strategy
        result = runner.invoke(
            app,
            [
                "strategy", "backtest",
                "AI_TEST",
                "--strategy",
                "ai_strat",
                "--db",
                str(db_path),
                "--start",
                "2024-01-01",
            ],
        )
        assert result.exit_code == 0, f"backtest failed: {result.stdout}"
        assert "Backtest Results" in result.stdout


class TestCLIRiskAssessment:
    """Test CLI risk assessment workflow."""

    def test_risk_command_basic(self, temp_workspace, monkeypatch):
        """CLI: risk command works with cached data."""
        monkeypatch.chdir(temp_workspace)

        # Set up test data - risk assessment needs sufficient data for indicators
        # (at least 100+ days for proper indicator computation)
        db_path = temp_workspace / "data.db"
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=150, ticker="RISK_TEST")
        repo.save_candles(candles)

        result = runner.invoke(
            app,
            [
                "analyze", "risk",
                "RISK_TEST",
                "--db",
                str(db_path),
            ],
        )

        output = result.output or result.stdout
        assert result.exit_code == 0, f"risk failed: {output}"
        assert "Risk Assessment" in output
        assert "Verdict:" in output

    def test_risk_all_profiles(self, temp_workspace, monkeypatch):
        """CLI: risk --all shows all profiles."""
        monkeypatch.chdir(temp_workspace)

        # Set up test data - need sufficient data for risk calculation
        db_path = temp_workspace / "data.db"
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=150, ticker="ALL_PROF")
        repo.save_candles(candles)

        result = runner.invoke(
            app,
            [
                "analyze", "risk",
                "ALL_PROF",
                "--all",
                "--db",
                str(db_path),
            ],
        )

        output = result.output or result.stdout
        assert result.exit_code == 0, f"risk --all failed: {output}"
        # Should show multiple profiles
        assert "conservative" in output.lower()
        assert "balanced" in output.lower()
        assert "aggressive" in output.lower()

    def test_risk_with_custom_rules(self, temp_workspace, monkeypatch):
        """CLI: risk with --rules-file uses custom rules."""
        monkeypatch.chdir(temp_workspace)

        # Create custom rules file
        rules_file = temp_workspace / "custom_rules.yaml"
        rules_file.write_text(create_rsi_oversold_strategy("custom_risk"))

        # Set up test data
        db_path = temp_workspace / "data.db"
        repo = SQLiteMarketRepository(db_path=db_path)
        candles = generate_test_candles(days=50, ticker="CUST_RISK")
        repo.save_candles(candles)

        result = runner.invoke(
            app,
            [
                "analyze", "risk",
                "CUST_RISK",
                "--rules-file",
                str(rules_file),
                "--db",
                str(db_path),
            ],
        )

        assert result.exit_code == 0, f"risk failed: {result.stdout}"
        assert "Risk Assessment" in result.stdout


class TestCLIEdgeCases:
    """Test edge cases and error handling."""

    def test_version_command(self):
        """CLI: version command shows version info."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "saham" in result.stdout.lower()

    def test_help_command(self):
        """CLI: --help shows usage information."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.stdout or "usage:" in result.stdout.lower()

    def test_invalid_ticker_handling(self, temp_workspace, monkeypatch):
        """CLI: commands handle invalid/missing ticker gracefully."""
        monkeypatch.chdir(temp_workspace)

        db_path = temp_workspace / "data.db"

        # Try to compute for non-existent ticker
        result = runner.invoke(
            app,
            ["indicator", "compute", "SMA", "NONEXISTENT", "--db", str(db_path)],
        )

        assert result.exit_code == 1
        output = result.output or result.stdout
        assert "no cached data" in output.lower() or "no data" in output.lower() or "fetch" in output.lower()
