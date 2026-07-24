"""CLI contracts for `saham research signal capture` (CLI-R3)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from src.adapters.cli import research_signal_backfill_commands as backfill_cmd
from src.adapters.cli.main import app
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsResponse,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)

runner = CliRunner()


def _patch_corpus_write(monkeypatch, backfill_cls=None):
    class DummyRepository:
        def __init__(self, *args, **kwargs):
            pass

    class DummyRequestBuilder:
        @classmethod
        def from_configs(cls, **kwargs):
            return cls()

    class DefaultBackfillUseCase:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def execute(self, request):
            return BackfillSignalObservationsResponse(
                requested_date_count=1,
                processed_date_count=1,
                skipped_date_count=0,
                saved_observation_count=2,
                generated_label_count=0,
                unavailable_label_count=0,
                processed_dates=(date(2026, 7, 21),),
                universe_size=1,
                evaluated_count=2,
                selected_count=2,
                rejected_count=0,
                unavailable_count=0,
                universe_membership_source="lq45@current",
                survivorship_limitation="current-universe only; survivorship-biased",
            )

    monkeypatch.setattr(
        backfill_cmd,
        "resolve_tickers",
        lambda universe, explicit, db_path, **kwargs: ["BBCA"],
    )
    monkeypatch.setattr(
        backfill_cmd,
        "load_accumulation_screener_config",
        lambda: object(),
    )
    monkeypatch.setattr(backfill_cmd, "load_swing_config", lambda: object())
    monkeypatch.setattr(
        backfill_cmd,
        "BuildSignalObservationScreenRequest",
        DummyRequestBuilder,
    )
    monkeypatch.setattr(
        backfill_cmd,
        "create_accumulation_screen_workflow_bundle",
        lambda **kwargs: SimpleNamespace(
            screen_use_case=object(), record_observations_use_case=object()
        ),
    )
    monkeypatch.setattr(
        backfill_cmd,
        "SQLiteCandidateObservationsRepository",
        DummyRepository,
    )
    monkeypatch.setattr(backfill_cmd, "SQLiteMarketRepository", DummyRepository)
    monkeypatch.setattr(
        backfill_cmd,
        "SQLiteSignalForwardLabelsRepository",
        DummyRepository,
    )
    monkeypatch.setattr(
        backfill_cmd,
        "BackfillSignalObservationsUseCase",
        backfill_cls or DefaultBackfillUseCase,
    )


def test_signal_capture_json_wires_single_session_without_labels(monkeypatch):
    captured = {}

    class CapturingBackfillUseCase:
        def __init__(self, **kwargs):
            captured["dependencies"] = kwargs

        def execute(self, request):
            captured["request"] = request
            return BackfillSignalObservationsResponse(
                requested_date_count=1,
                processed_date_count=1,
                skipped_date_count=0,
                saved_observation_count=2,
                generated_label_count=0,
                unavailable_label_count=0,
                processed_dates=(date(2026, 7, 21),),
                universe_size=1,
                evaluated_count=2,
                selected_count=2,
                rejected_count=0,
                unavailable_count=0,
                universe_membership_source="lq45@current",
            )

    _patch_corpus_write(monkeypatch, CapturingBackfillUseCase)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "capture",
            "--universe",
            "lq45",
            "--session",
            "2026-07-21",
            "--contract",
            ACCUMULATION_DISCOVERY_CONTRACT,
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["saved_observation_count"] == 2
    assert payload["generated_label_count"] == 0
    assert captured["request"].start_date == date(2026, 7, 21)
    assert captured["request"].end_date == date(2026, 7, 21)
    assert captured["request"].generate_labels is False
    assert captured["request"].universe_membership_source == "lq45@current"
    assert captured["dependencies"]["label_generation_use_case"] is None
    identity = captured["dependencies"]["observation_identity"]
    assert identity.observation_contract == ACCUMULATION_DISCOVERY_CONTRACT


def test_signal_capture_rejects_unsupported_contract(tmp_path):
    db_path = tmp_path / "capture.db"
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "capture",
            "--universe",
            "lq45",
            "--session",
            "2026-07-21",
            "--contract",
            "legacy-accumulation-candidates",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    assert "Unsupported --contract" in result.stderr
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM signal_forward_labels").fetchone()[0] == 0


def test_signal_capture_rejects_invalid_session(tmp_path):
    db_path = tmp_path / "capture.db"
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "capture",
            "--universe",
            "lq45",
            "--session",
            "not-a-date",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    assert "Invalid --session" in result.stderr
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM signal_forward_labels").fetchone()[0] == 0


def test_analyze_signal_inspect_still_read_only_after_capture_mount(tmp_path):
    """CLI-R3 negative: analyze signal inspect must not write tables."""
    db_path = tmp_path / "inspect.db"
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)

    result = runner.invoke(
        app,
        [
            "analyze",
            "signal",
            "inspect",
            "BBCA",
            "--as-of",
            "not-a-date",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM signal_forward_labels").fetchone()[0] == 0
