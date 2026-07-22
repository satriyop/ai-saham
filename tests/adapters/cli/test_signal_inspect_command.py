"""DQ-011 — thin CLI contracts for `saham analyze signal-inspect`."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from src.adapters.cli import analyze_signal_inspect_commands as inspect_cmd
from src.adapters.cli.main import app
from src.application.dto.inspect_canonical_signal import (
    InspectCanonicalSignalContract,
    InspectCanonicalSignalResponse,
    InspectCanonicalSignalStatus,
)
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)

runner = CliRunner()


def _count_rows(db_path: Path, table: str) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _init_signal_tables(db_path: Path) -> None:
    SQLiteCandidateObservationsRepository(db_path)
    SQLiteSignalForwardLabelsRepository(db_path)


def _patch_inspect_use_case(monkeypatch, response: InspectCanonicalSignalResponse) -> None:
    monkeypatch.setattr(
        inspect_cmd,
        "load_app_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(db_path="unused.db")),
    )
    monkeypatch.setattr(inspect_cmd, "load_swing_config", lambda: object())
    monkeypatch.setattr(inspect_cmd, "load_accumulation_screener_config", lambda: object())
    monkeypatch.setattr(
        inspect_cmd,
        "BuildSignalObservationScreenRequest",
        SimpleNamespace(from_configs=staticmethod(lambda **_kwargs: object())),
    )
    monkeypatch.setattr(
        inspect_cmd,
        "create_accumulation_screen_workflow_bundle",
        lambda **_kwargs: SimpleNamespace(screen_use_case=object()),
    )
    monkeypatch.setattr(inspect_cmd, "SQLiteMarketRepository", lambda _path: object())
    monkeypatch.setattr(inspect_cmd, "EffectiveMarketSessionResolver", lambda _repo: object())

    class FakeUseCase:
        def __init__(self, **_kwargs):
            pass

        def execute(self, request):
            assert request.ticker == response.ticker
            return response

    monkeypatch.setattr(inspect_cmd, "InspectCanonicalSignalUseCase", FakeUseCase)


def test_signal_inspect_rejects_invalid_date(tmp_path):
    db_path = tmp_path / "inspect.db"
    _init_signal_tables(db_path)
    before_obs = _count_rows(db_path, "candidate_observations")
    before_labels = _count_rows(db_path, "signal_forward_labels")

    result = runner.invoke(
        app,
        [
            "analyze",
            "signal-inspect",
            "BBCA",
            "--date",
            "not-a-date",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    assert "Invalid --date" in result.stderr
    assert _count_rows(db_path, "candidate_observations") == before_obs
    assert _count_rows(db_path, "signal_forward_labels") == before_labels


def test_signal_inspect_json_ok_is_read_only(monkeypatch, tmp_path):
    db_path = tmp_path / "inspect.db"
    _init_signal_tables(db_path)
    day = date(2026, 7, 7)
    _patch_inspect_use_case(
        monkeypatch,
        InspectCanonicalSignalResponse(
            status=InspectCanonicalSignalStatus.OK,
            contract=InspectCanonicalSignalContract.ACCUMULATION_FLOW,
            ticker="BBCA",
            as_of_date=day,
            notes=("read-only fixture",),
        ),
    )
    before_obs = _count_rows(db_path, "candidate_observations")
    before_labels = _count_rows(db_path, "signal_forward_labels")

    result = runner.invoke(
        app,
        [
            "analyze",
            "signal-inspect",
            "BBCA",
            "--date",
            day.isoformat(),
            "--format",
            "json",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "OK"
    assert payload["contract"] == "accumulation-flow"
    assert payload["ticker"] == "BBCA"
    assert "notes" in payload
    assert _count_rows(db_path, "candidate_observations") == before_obs
    assert _count_rows(db_path, "signal_forward_labels") == before_labels


def test_signal_inspect_unavailable_prints_json_then_exits_one(monkeypatch, tmp_path):
    db_path = tmp_path / "inspect.db"
    _init_signal_tables(db_path)
    day = date(2026, 7, 7)
    _patch_inspect_use_case(
        monkeypatch,
        InspectCanonicalSignalResponse(
            status=InspectCanonicalSignalStatus.UNAVAILABLE,
            contract=InspectCanonicalSignalContract.ACCUMULATION_FLOW,
            ticker="BBCA",
            as_of_date=day,
            reasons=("no candles",),
        ),
    )

    result = runner.invoke(
        app,
        [
            "analyze",
            "signal-inspect",
            "BBCA",
            "--date",
            day.isoformat(),
            "--format",
            "json",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "UNAVAILABLE"
    assert payload["reasons"] == ["no candles"]
    assert _count_rows(db_path, "candidate_observations") == 0
    assert _count_rows(db_path, "signal_forward_labels") == 0
