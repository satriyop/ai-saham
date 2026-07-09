from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from typer.testing import CliRunner

from src.adapters.cli import analyze_signal_commands
from src.adapters.cli.main import app
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsResponse,
)

runner = CliRunner()


def test_signal_backfill_observations_json_output_is_stable(monkeypatch):
    captured = {}

    class FakeBackfillUseCase:
        def __init__(self, **kwargs):
            captured["dependencies"] = kwargs

        def execute(self, request):
            captured["request"] = request
            return BackfillSignalObservationsResponse(
                requested_date_count=2,
                processed_date_count=1,
                skipped_date_count=1,
                saved_observation_count=3,
                generated_label_count=1,
                unavailable_label_count=0,
                processed_dates=(date(2026, 6, 1),),
                notes=("candidate_observations are timestamped",),
            )

    _patch_command_dependencies(monkeypatch, FakeBackfillUseCase)

    result = runner.invoke(
        app,
        [
            "analyze",
            "signal-backfill-observations",
            "--universe",
            "lq45",
            "--start",
            "2026-06-01",
            "--end",
            "2026-06-02",
            "--horizon",
            "SWING_10D",
            "--generate-labels",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["requested_date_count"] == 2
    assert payload["processed_dates"] == ["2026-06-01"]
    assert payload["saved_observation_count"] == 3
    assert captured["request"].tickers == ("BBCA",)
    assert captured["request"].generate_labels is True


def test_signal_backfill_observations_wires_evaluate_market_context(monkeypatch):
    captured = {}
    market_context_calls = []

    class FakeBackfillUseCase:
        def __init__(self, **kwargs):
            captured["dependencies"] = kwargs

        def execute(self, request):
            captured["request"] = request
            return BackfillSignalObservationsResponse(
                requested_date_count=2,
                processed_date_count=1,
                skipped_date_count=1,
                saved_observation_count=3,
                generated_label_count=1,
                unavailable_label_count=0,
                processed_dates=(date(2026, 6, 1),),
                notes=("candidate_observations are timestamped",),
            )

    def fake_evaluate_market_context(*, db_path, as_of_date, universe):
        market_context_calls.append(
            {"db_path": db_path, "as_of_date": as_of_date, "universe": universe}
        )
        return SimpleNamespace(sentinel="fake-market-context")

    _patch_command_dependencies(monkeypatch, FakeBackfillUseCase)
    monkeypatch.setattr(
        analyze_signal_commands,
        "evaluate_market_context",
        fake_evaluate_market_context,
    )

    result = runner.invoke(
        app,
        [
            "analyze",
            "signal-backfill-observations",
            "--universe",
            "lq45",
            "--start",
            "2026-06-01",
            "--end",
            "2026-06-02",
        ],
    )

    assert result.exit_code == 0, result.output
    dependencies = captured["dependencies"]
    assert dependencies["evaluate_market_context"] is not None
    assert callable(dependencies["evaluate_market_context"])

    # Prove the wrapper is bound to the right db_path/universe by invoking it
    # directly and inspecting what it forwards to evaluate_market_context.
    result_context = dependencies["evaluate_market_context"](as_of_date=date(2026, 6, 1))
    assert result_context.sentinel == "fake-market-context"
    assert len(market_context_calls) == 1
    call = market_context_calls[0]
    assert call["universe"] == "lq45"
    assert call["as_of_date"] == date(2026, 6, 1)
    assert call["db_path"] == analyze_signal_commands.DEFAULT_DB_PATH


def test_signal_backfill_observations_rejects_invalid_date(monkeypatch):
    _patch_command_dependencies(monkeypatch)

    result = runner.invoke(
        app,
        [
            "analyze",
            "signal-backfill-observations",
            "--universe",
            "lq45",
            "--start",
            "not-a-date",
            "--end",
            "2026-06-02",
        ],
    )

    assert result.exit_code == 1
    assert "Invalid date" in result.stderr


def test_signal_backfill_observations_rejects_end_before_start(monkeypatch):
    _patch_command_dependencies(monkeypatch)

    result = runner.invoke(
        app,
        [
            "analyze",
            "signal-backfill-observations",
            "--universe",
            "lq45",
            "--start",
            "2026-06-02",
            "--end",
            "2026-06-01",
        ],
    )

    assert result.exit_code == 1
    assert "--end must be on or after --start" in result.stderr


def _patch_command_dependencies(monkeypatch, backfill_cls=None):
    class DummyRepository:
        def __init__(self, *args, **kwargs):
            pass

    class DummyLabelUseCase:
        def __init__(self, *args, **kwargs):
            pass

    class DummyRequestBuilder:
        @classmethod
        def from_configs(cls, **kwargs):
            return cls()

    class DefaultBackfillUseCase:
        def __init__(self, **kwargs):
            pass

        def execute(self, request):
            return BackfillSignalObservationsResponse(
                requested_date_count=0,
                processed_date_count=0,
                skipped_date_count=0,
                saved_observation_count=0,
                generated_label_count=0,
                unavailable_label_count=0,
            )

    monkeypatch.setattr(
        analyze_signal_commands,
        "resolve_tickers",
        lambda universe, explicit, db_path: ["BBCA"],
    )
    monkeypatch.setattr(
        analyze_signal_commands,
        "load_accumulation_screener_config",
        lambda: object(),
    )
    monkeypatch.setattr(analyze_signal_commands, "load_swing_config", lambda: object())
    monkeypatch.setattr(
        analyze_signal_commands,
        "BuildSignalObservationScreenRequest",
        DummyRequestBuilder,
    )
    monkeypatch.setattr(
        analyze_signal_commands,
        "create_accumulation_screen_workflow",
        lambda **kwargs: SimpleNamespace(use_case=object()),
    )
    monkeypatch.setattr(
        analyze_signal_commands,
        "SQLiteCandidateObservationsRepository",
        DummyRepository,
    )
    monkeypatch.setattr(analyze_signal_commands, "SQLiteMarketRepository", DummyRepository)
    monkeypatch.setattr(
        analyze_signal_commands,
        "SQLiteSignalForwardLabelsRepository",
        DummyRepository,
    )
    monkeypatch.setattr(
        analyze_signal_commands,
        "GenerateSignalForwardLabelsUseCase",
        DummyLabelUseCase,
    )
    monkeypatch.setattr(
        analyze_signal_commands,
        "BackfillSignalObservationsUseCase",
        backfill_cls or DefaultBackfillUseCase,
    )
