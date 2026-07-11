"""
CLI smoke tests for `saham fetch calendar`.

Follows the CliRunner + monkeypatch convention from test_fetch_universe_commands.py
(patching get_stockbit_session) and test_fetch_iev_commands.py (CliRunner +
`from src.adapters.cli.main import app`). The use case itself is exercised in
test_sync_corporate_action_calendar_use_case.py — these tests only verify the
adapter's argument parsing, authentication gate, and output formatting/exit
codes.
"""

from pathlib import Path

from typer.testing import CliRunner

import src.adapters.cli.fetch_calendar_commands as calendar_commands
import src.infrastructure.browser.stockbit_api_client as _stockbit_api_client
from src.adapters.cli.main import app
from src.application.services.stockbit_session import StockbitSession
from src.application.use_case.sync_corporate_action_calendar_use_case import (
    SyncCorporateActionCalendarResponse,
)

runner = CliRunner()


def _mock_authenticated_session(monkeypatch):
    """fetch_calendar_commands imports get_stockbit_session via a direct
    `from ... import` binding, so the name must be patched on the
    calendar_commands module itself — patching src.application.services
    .stockbit_session.get_stockbit_session would not affect the already-bound
    reference."""
    fake_client = object.__new__(_stockbit_api_client.StockbitApiClient)
    monkeypatch.setattr(
        calendar_commands,
        "get_stockbit_session",
        lambda: StockbitSession(api_client=fake_client, authenticated=True),
    )
    return fake_client


def _mock_unauthenticated_session(monkeypatch):
    monkeypatch.setattr(calendar_commands, "get_stockbit_session", lambda: None)


class FakeUseCase:
    """Stub SyncCorporateActionCalendarUseCase — returns a scripted response."""

    def __init__(self, response: SyncCorporateActionCalendarResponse) -> None:
        self._response = response
        self.execute_calls: list = []

    def execute(self, request):
        self.execute_calls.append(request)
        return self._response


def _wire_fake_use_case(monkeypatch, response: SyncCorporateActionCalendarResponse) -> FakeUseCase:
    fake_uc = FakeUseCase(response)
    monkeypatch.setattr(
        calendar_commands,
        "SyncCorporateActionCalendarUseCase",
        lambda provider, repository: fake_uc,
    )
    monkeypatch.setattr(
        calendar_commands, "StockbitCorporateActionCalendarProvider", lambda api_client: object()
    )
    monkeypatch.setattr(
        calendar_commands, "SQLiteCorporateActionCalendarRepository", lambda db_path: object()
    )
    return fake_uc


def _response(**overrides) -> SyncCorporateActionCalendarResponse:
    kwargs = dict(
        status="success",
        fetched_count=1,
        stored_count=1,
        event_type_counts={"dividend": 1},
        errors=(),
        from_cache=False,
    )
    kwargs.update(overrides)
    return SyncCorporateActionCalendarResponse(**kwargs)


class TestNotAuthenticated:
    def test_no_session_prints_error_and_exits_1(self, monkeypatch, tmp_path: Path):
        _mock_unauthenticated_session(monkeypatch)
        result = runner.invoke(app, ["fetch", "calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 1
        assert "Not authenticated." in result.stdout + (result.stderr or "")

    def test_unauthenticated_session_object_prints_error_and_exits_1(self, monkeypatch, tmp_path: Path):
        fake_client = object.__new__(_stockbit_api_client.StockbitApiClient)
        monkeypatch.setattr(
            calendar_commands,
            "get_stockbit_session",
            lambda: StockbitSession(api_client=fake_client, authenticated=False),
        )
        result = runner.invoke(app, ["fetch", "calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 1
        assert "Not authenticated." in result.stdout + (result.stderr or "")


class TestInvalidTypes:
    def test_unsupported_type_name_exits_1_with_supported_list(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        result = runner.invoke(
            app,
            ["fetch", "calendar", "--types", "warrant", "--db", str(tmp_path / "x.db")],
        )
        assert result.exit_code == 1
        combined = result.stdout + (result.stderr or "")
        assert "Unsupported event type" in combined
        assert "warrant" in combined
        for supported in (
            "dividend",
            "stock_split",
            "reverse_split",
            "rights_issue",
            "bonus",
            "tender_offer",
            "rups",
            "pubex",
            "ipo",
        ):
            assert supported in combined


class TestRefreshFlagThreading:
    def test_refresh_flag_sets_force_remote_fetch_true(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        fake_uc = _wire_fake_use_case(monkeypatch, _response())
        runner.invoke(app, ["fetch", "calendar", "--refresh", "--db", str(tmp_path / "x.db")])
        assert len(fake_uc.execute_calls) == 1
        assert fake_uc.execute_calls[0].force_remote_fetch is True

    def test_no_refresh_flag_leaves_force_remote_fetch_false(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        fake_uc = _wire_fake_use_case(monkeypatch, _response())
        runner.invoke(app, ["fetch", "calendar", "--db", str(tmp_path / "x.db")])
        assert fake_uc.execute_calls[0].force_remote_fetch is False


class TestFromCacheOutput:
    def test_from_cache_true_prints_already_synced_message_no_error_exit(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        _wire_fake_use_case(
            monkeypatch,
            _response(status="cached", from_cache=True, fetched_count=0, stored_count=0, event_type_counts={}),
        )
        result = runner.invoke(app, ["fetch", "calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 0
        assert "Already synced today" in result.stdout


class TestFailedStatus:
    def test_status_failed_prints_red_message_and_exits_1(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        _wire_fake_use_case(
            monkeypatch,
            _response(
                status="failed",
                fetched_count=0,
                stored_count=0,
                event_type_counts={},
                errors=("network down",),
            ),
        )
        result = runner.invoke(app, ["fetch", "calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 1
        combined = result.stdout + (result.stderr or "")
        assert "Calendar sync failed." in combined
        assert "network down" in combined


class TestSuccessVsPartialOutput:
    def test_success_status_prints_success_line(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        _wire_fake_use_case(monkeypatch, _response(status="success"))
        result = runner.invoke(app, ["fetch", "calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 0
        assert "Calendar sync: success" in result.stdout

    def test_partial_status_prints_partial_line_with_warnings(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        _wire_fake_use_case(
            monkeypatch,
            _response(status="partial", errors=("ipo:auth-or-network",)),
        )
        result = runner.invoke(app, ["fetch", "calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 0
        assert "Calendar sync: partial" in result.stdout
        assert "ipo:auth-or-network" in result.stdout


def test_help_smoke():
    result = runner.invoke(app, ["fetch", "calendar", "--help"])
    assert result.exit_code == 0
    assert "corporate action calendar" in result.stdout.lower()
