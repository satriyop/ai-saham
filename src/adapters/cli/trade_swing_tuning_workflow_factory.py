"""
Factory for the `saham trade tune-swing` workflow.

Layer: Adapter

Owns CLI/infrastructure wiring (runner config loading, the swing backtest
runner callable, the swing tuning document loader, and the review journal)
so trade_swing_tuning_commands.py can stay focused on flag parsing, request
construction, execution, and rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.adapters.cli.trade_swing_backtest_runner import (
    SwingBacktestRunnerConfig,
    _run_swing_backtest,
    load_swing_backtest_runner_config,
)
from src.application.services.swing_tuning_review_journal import SwingTuningReviewJournal
from src.application.use_case.run_swing_tuning_review_use_case import (
    RunSwingTuningReviewUseCase,
    SwingTuningRunnerDefaults,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)


def _defaults_from_runner_config(
    runner_config: SwingBacktestRunnerConfig,
) -> SwingTuningRunnerDefaults:
    backtest_config = runner_config.backtest_config
    return SwingTuningRunnerDefaults(
        capital=backtest_config.capital,
        risk_pct=backtest_config.risk_pct,
        max_positions=backtest_config.max_positions,
        take_profit_pct=backtest_config.take_profit_pct,
        stop_loss_pct=backtest_config.stop_loss_pct,
        max_hold_days=backtest_config.max_hold_days,
        cost_bps=backtest_config.cost_bps,
    )


def create_run_swing_tuning_review_workflow(
    *,
    journal_path: Path | None,
) -> RunSwingTuningReviewUseCase:
    """Build the swing tuning review workflow use case with CLI infrastructure."""
    runner_config = load_swing_backtest_runner_config()

    def _backtest_runner(**kwargs: Any):
        return _run_swing_backtest(config=runner_config, **kwargs)

    resolved_journal_path = journal_path or Path(
        load_app_config().storage.swing_tuning_review_journal
    )
    review_journal = SwingTuningReviewJournal(
        SwingTuningReviewJsonlWriter(resolved_journal_path)
    )

    return RunSwingTuningReviewUseCase(
        backtest_runner=_backtest_runner,
        runner_defaults=_defaults_from_runner_config(runner_config),
        document_loader=swing_tuning_document_loader(),
        review_journal=review_journal,
    )
