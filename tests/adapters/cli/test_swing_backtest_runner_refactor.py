from unittest.mock import MagicMock, patch

from src.adapters.cli.analyze_swing_commands import swing
from src.adapters.cli.analyze_swing_compare_commands import swing_compare
from src.adapters.cli.trade_swing_backtest_runner import (
    SwingBacktestRunnerConfig,
    _run_swing_backtest,
)
from src.adapters.cli.trade_swing_tuning_commands import swing_tune


def test_run_swing_backtest_accepts_explicit_config():
    # Setup mock config
    mock_config = MagicMock(spec=SwingBacktestRunnerConfig)
    mock_config.accumulation_config = MagicMock()
    mock_config.accumulation_config.derived_features = {}
    mock_config.swing_config = MagicMock()
    mock_config.swing_config.setup_targets = {}
    mock_config.swing_config.resistance_gate_enabled = False
    mock_config.swing_config.resistance_headroom_min_pct = 0.0
    mock_config.swing_config.ex_date_warning_days = 0
    mock_config.backtest_config = MagicMock()
    mock_config.backtest_config.forward_data_lookahead_days = 0
    mock_config.backtest_config.same_day_exit_priority = ""
    mock_config.backtest_config.attribution_high_min_score = 70
    mock_config.backtest_config.attribution_mid_min_score = 50
    mock_config.setup_config = MagicMock()

    runner_pkg = "src.adapters.cli.trade_swing_backtest_runner"
    with patch(f"{runner_pkg}.load_swing_backtest_runner_config") as mock_load, \
         patch(f"{runner_pkg}.resolve_tickers", return_value=["BBCA"]), \
         patch(f"{runner_pkg}.SwingBacktestUseCase") as mock_use_case_class:

        mock_use_case = MagicMock()
        mock_use_case_class.return_value = mock_use_case

        # Call with explicit config
        _run_swing_backtest(
            tickers=["BBCA"],
            universe=None,
            setup="foreign-bounce",
            start="2026-06-19",
            end=None,
            capital=10000000,
            risk_pct=1.0,
            max_positions=3,
            take_profit=5.0,
            stop_loss=5.0,
            max_hold=20,
            cost_bps=20.0,
            with_regime=False,
            allow_regimes=None,
            benchmark="COMPOSITE",
            db_path=None,
            announce=False,
            config=mock_config,
        )

        # Verification: load_swing_backtest_runner_config should not be called
        mock_load.assert_not_called()


def test_tuning_commands_delegates_raw_options_to_workflow():
    # Default resolution now lives in RunSwingTuningReviewUseCase (see
    # tests/application/use_case/test_run_swing_tuning_review_use_case.py).
    # This adapter test only verifies swing_tune builds a request with the
    # raw CLI intent and delegates to the injected workflow.
    tune_pkg = "src.adapters.cli.trade_swing_tuning_commands"
    mock_workflow = MagicMock()
    mock_result = MagicMock()
    mock_result.is_split_message = None
    mock_result.persistence = None
    mock_result.patch_payload = None
    mock_result.payload = {}
    mock_workflow.execute.return_value = mock_result

    with patch(
        f"{tune_pkg}.create_run_swing_tuning_review_workflow",
        return_value=mock_workflow,
    ), patch(f"{tune_pkg}.display_swing_backtest"):

        swing_tune(
            tickers=["BBCA"],
            capital=None,
            risk_pct=None,
            max_positions=None,
            take_profit=None,
            stop_loss=None,
            max_hold=None,
            cost_bps=None,
        )

        mock_workflow.execute.assert_called_once()
        request = mock_workflow.execute.call_args[0][0]
        assert request.tickers == ["BBCA"]
        assert request.capital is None
        assert request.risk_pct is None
        assert request.max_positions is None
        assert request.take_profit is None
        assert request.stop_loss is None
        assert request.max_hold is None
        assert request.cost_bps is None


def test_analyze_commands_use_load_config_per_invocation():
    mock_config = MagicMock()
    mock_config.swing_backtest_config = MagicMock()
    mock_config.swing_backtest_config.capital = 10000000
    mock_config.swing_backtest_config.risk_pct = 1.0
    mock_config.swing_backtest_config.max_positions = 3
    mock_config.swing_backtest_config.take_profit_pct = 5.0
    mock_config.swing_backtest_config.stop_loss_pct = 5.0
    mock_config.swing_backtest_config.max_hold_days = 20
    mock_config.swing_backtest_config.cost_bps = 20.0
    mock_config.swing_backtest_config.forward_data_lookahead_days = 0
    mock_config.swing_backtest_config.same_day_exit_priority = ""
    mock_config.swing_config = MagicMock()
    mock_config.swing_config.resistance_gate_enabled = False
    mock_config.swing_config.resistance_headroom_min_pct = 0.0
    mock_config.swing_config.ex_date_warning_days = 0
    mock_config.setup_config = MagicMock()
    mock_config.accumulation_screener_config = MagicMock()
    mock_config.accumulation_screener_config.derived_features = {}

    analyze_pkg = "src.adapters.cli.analyze_swing_commands"
    patch_loader = patch(
        f"{analyze_pkg}.load_analyze_swing_command_config",
        return_value=mock_config
    )
    with patch_loader as mock_load, \
         patch(f"{analyze_pkg}.create_swing_analysis_workflow") as mock_wf_func, \
         patch(f"{analyze_pkg}.print_swing_output"):

        mock_wf = MagicMock()
        mock_wf_func.return_value = mock_wf

        swing(ticker="BBCA")

        mock_load.assert_called_once()

    compare_pkg = "src.adapters.cli.analyze_swing_compare_commands"
    patch_compare_loader = patch(
        f"{compare_pkg}.load_analyze_swing_command_config",
        return_value=mock_config
    )
    with patch_compare_loader as mock_load, \
         patch(f"{compare_pkg}.resolve_tickers", return_value=["BBCA"]), \
         patch(f"{compare_pkg}.SwingBacktestUseCase") as mock_uc_class, \
         patch(f"{compare_pkg}.display_swing_compare"):

        mock_uc = MagicMock()
        mock_uc_class.return_value = mock_uc

        swing_compare(tickers=["BBCA"])

        mock_load.assert_called_once()
