"""Tests for the `saham trade tune-swing` workflow factory."""

from pathlib import Path

from src.adapters.cli import trade_swing_tuning_workflow_factory as factory
from src.application.services.swing_tuning_review_journal import SwingTuningReviewJournal
from src.application.use_case.run_swing_tuning_review_use_case import (
    RunSwingTuningReviewUseCase,
)
from src.infrastructure.config.app_config import load_app_config


class _FakeBacktestConfig:
    capital = 111
    risk_pct = 0.42
    max_positions = 7
    take_profit_pct = 6.0
    stop_loss_pct = 4.0
    max_hold_days = 12
    cost_bps = 25.0


class _FakeRunnerConfig:
    backtest_config = _FakeBacktestConfig()


def _patch_common(monkeypatch, runner_config=None):
    monkeypatch.setattr(
        factory,
        "load_swing_backtest_runner_config",
        lambda: runner_config or _FakeRunnerConfig(),
    )
    monkeypatch.setattr(
        factory, "swing_tuning_document_loader", lambda: (lambda path: None)
    )


def test_factory_returns_run_swing_tuning_review_use_case(monkeypatch):
    _patch_common(monkeypatch)

    workflow = factory.create_run_swing_tuning_review_workflow(journal_path=None)

    assert isinstance(workflow, RunSwingTuningReviewUseCase)


def test_factory_maps_backtest_config_fields_into_runner_defaults(monkeypatch):
    runner_config = _FakeRunnerConfig()
    _patch_common(monkeypatch, runner_config=runner_config)

    workflow = factory.create_run_swing_tuning_review_workflow(journal_path=None)

    defaults = workflow._runner_defaults
    assert defaults.capital == runner_config.backtest_config.capital
    assert defaults.risk_pct == runner_config.backtest_config.risk_pct
    assert defaults.max_positions == runner_config.backtest_config.max_positions
    assert defaults.take_profit_pct == runner_config.backtest_config.take_profit_pct
    assert defaults.stop_loss_pct == runner_config.backtest_config.stop_loss_pct
    assert defaults.max_hold_days == runner_config.backtest_config.max_hold_days
    assert defaults.cost_bps == runner_config.backtest_config.cost_bps


def test_factory_injects_backtest_runner_that_calls_run_swing_backtest_with_wired_config(
    monkeypatch,
):
    runner_config = _FakeRunnerConfig()
    _patch_common(monkeypatch, runner_config=runner_config)
    captured = {}

    def _fake_run_swing_backtest(*, config, **kwargs):
        captured["config"] = config
        captured["kwargs"] = kwargs
        return "sentinel-response"

    monkeypatch.setattr(factory, "_run_swing_backtest", _fake_run_swing_backtest)

    workflow = factory.create_run_swing_tuning_review_workflow(journal_path=None)
    result = workflow._backtest_runner(tickers=["BBCA"], start="2026-01-01")

    assert result == "sentinel-response"
    assert captured["config"] is runner_config
    assert captured["kwargs"] == {"tickers": ["BBCA"], "start": "2026-01-01"}


def test_factory_always_injects_review_journal_with_default_path(monkeypatch):
    _patch_common(monkeypatch)
    captured_paths = []

    class _FakeWriter:
        def __init__(self, path):
            captured_paths.append(path)
            self.path = path

    monkeypatch.setattr(factory, "SwingTuningReviewJsonlWriter", _FakeWriter)

    workflow = factory.create_run_swing_tuning_review_workflow(journal_path=None)

    assert isinstance(workflow._review_journal, SwingTuningReviewJournal)
    assert captured_paths == [Path(load_app_config().storage.swing_tuning_review_journal)]


def test_factory_injects_review_journal_with_given_path(monkeypatch):
    _patch_common(monkeypatch)
    captured_paths = []

    class _FakeWriter:
        def __init__(self, path):
            captured_paths.append(path)
            self.path = path

    monkeypatch.setattr(factory, "SwingTuningReviewJsonlWriter", _FakeWriter)
    custom_path = Path("/tmp/custom-journal.jsonl")

    workflow = factory.create_run_swing_tuning_review_workflow(journal_path=custom_path)

    assert isinstance(workflow._review_journal, SwingTuningReviewJournal)
    assert captured_paths == [custom_path]


def test_commands_module_no_longer_imports_moved_identifiers():
    import src.adapters.cli.trade_swing_tuning_commands as mod

    for name in (
        "_run_swing_backtest",
        "SwingTuningReviewJournal",
        "SwingTuningReviewJsonlWriter",
        "swing_tuning_document_loader",
        "build_tuning_readiness_plan",
        "build_tuning_proposal_draft",
        "build_tuning_config_diff_draft",
    ):
        assert not hasattr(mod, name), f"{name} should not be in trade_swing_tuning_commands"
