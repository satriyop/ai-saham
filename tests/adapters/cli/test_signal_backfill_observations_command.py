from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from src.adapters.cli import analyze_signal_backfill_commands as analyze_signal_commands
from src.adapters.cli.main import app
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsResponse,
)
from src.infrastructure.config.app_config import load_app_config

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
                universe_size=1,
                evaluated_count=3,
                selected_count=3,
                rejected_count=0,
                unavailable_count=0,
                universe_membership_source="lq45@current",
                survivorship_limitation="current-universe only; survivorship-biased",
                ticker_exclusions=(),
            )

    _patch_command_dependencies(monkeypatch, FakeBackfillUseCase)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "backfill",
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
    # DQ-003 Slice B reporting keys are present in --format json.
    for key in (
        "universe_size",
        "evaluated_count",
        "selected_count",
        "rejected_count",
        "unavailable_count",
        "universe_membership_source",
        "survivorship_limitation",
        "ticker_exclusions",
    ):
        assert key in payload
    assert payload["universe_membership_source"] == "lq45@current"
    assert payload["survivorship_limitation"] is not None
    assert captured["request"].tickers == ("BBCA",)
    assert captured["request"].generate_labels is True
    # The adapter passes the current-universe membership identity (identity only;
    # the use case owns the survivorship policy derived from it).
    assert captured["request"].universe_membership_source == "lq45@current"


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
            "research",
            "signal",
            "backfill",
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
    assert call["db_path"] == Path(load_app_config().storage.db_path)


def test_signal_backfill_observations_rejects_invalid_date(monkeypatch):
    _patch_command_dependencies(monkeypatch)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "backfill",
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
            "research",
            "signal",
            "backfill",
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
        lambda universe, explicit, db_path, **kwargs: ["BBCA"],
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
        "create_accumulation_screen_workflow_bundle",
        lambda **kwargs: SimpleNamespace(
            screen_use_case=object(), record_observations_use_case=object()
        ),
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


def test_read_scoring_config_canonical_reads_full_scoring_set():
    """The adapter helper reads the full scoring config set into a
    deterministic, content-bearing string (no hashing)."""
    cfg = load_app_config()
    canonical = analyze_signal_commands._read_scoring_config_canonical(cfg.config_paths)
    assert isinstance(canonical, str)
    for rel_path in (
        cfg.config_paths.accumulation_screener,
        cfg.config_paths.signal_engine,
        cfg.config_paths.market_context_engine,
        cfg.config_paths.ticker_profile,
    ):
        assert f"# path: {rel_path}" in canonical
    # It carries raw config content, not a digest.
    assert len(canonical) > 64


def test_adapter_delegates_hashing_to_application_resolver(monkeypatch):
    """Architecture boundary: the adapter passes raw config content to the
    application resolver and computes NO hash itself. The resolved id must flow
    to the backfill use case verbatim."""
    from src.domain.value_objects.signal_artifact_identity import (
        SemanticCompatibilityId,
    )
    from src.domain.value_objects.signal_semantic_contract import (
        ACCUMULATION_DISCOVERY_CONTRACT,
    )

    captured = {}
    spy_return = SemanticCompatibilityId("sha256:" + "e" * 64)

    def _spy_resolver(resolved_config_canonical):
        captured["resolver_arg"] = resolved_config_canonical
        return spy_return

    class CapturingBackfillUseCase:
        def __init__(self, **kwargs):
            captured["dependencies"] = kwargs

        def execute(self, request):
            return BackfillSignalObservationsResponse(
                requested_date_count=0,
                processed_date_count=0,
                skipped_date_count=0,
                saved_observation_count=0,
                generated_label_count=0,
                unavailable_label_count=0,
            )

    _patch_command_dependencies(monkeypatch, CapturingBackfillUseCase)
    monkeypatch.setattr(
        analyze_signal_commands,
        "resolve_lean_semantic_compatibility_id",
        _spy_resolver,
    )

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "backfill",
            "--universe",
            "lq45",
            "--start",
            "2026-06-01",
            "--end",
            "2026-06-02",
        ],
    )

    assert result.exit_code == 0, result.output
    # The adapter passed raw config CONTENT (a long YAML string), not a hash.
    resolver_arg = captured["resolver_arg"]
    assert isinstance(resolver_arg, str)
    assert "# path: " in resolver_arg
    assert len(resolver_arg) > 64
    # The application-resolved id flows into the use case verbatim.
    identity = captured["dependencies"]["observation_identity"]
    assert identity.observation_contract == ACCUMULATION_DISCOVERY_CONTRACT
    assert identity.semantic_compatibility_id is spy_return


def test_invalid_dates_do_not_write_signal_tables(tmp_path):
    """DQ-011 D11-5: validation failure before backfill must leave DB untouched."""
    import sqlite3

    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )

    db_path = tmp_path / "backfill.db"
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "backfill",
            "--universe",
            "lq45",
            "--start",
            "bad-date",
            "--end",
            "2026-06-02",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    assert "Invalid date" in result.stderr
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM signal_forward_labels").fetchone()[0] == 0


def test_end_before_start_does_not_write_signal_tables(tmp_path):
    """DQ-011 D11-5: range validation must not touch observation/label tables."""
    import sqlite3

    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )

    db_path = tmp_path / "backfill.db"
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)

    result = runner.invoke(
        app,
        [
            "research",
            "signal",
            "backfill",
            "--universe",
            "lq45",
            "--start",
            "2026-06-02",
            "--end",
            "2026-06-01",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    assert "--end must be on or after --start" in result.stderr
    with sqlite3.connect(str(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM candidate_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM signal_forward_labels").fetchone()[0] == 0
