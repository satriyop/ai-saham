"""CLI smoke tests for `saham fetch macro-calendar`."""

from pathlib import Path

from typer.testing import CliRunner

import src.adapters.cli.fetch_macro_calendar_commands as macro_commands
import src.infrastructure.browser.stockbit_api_client as _stockbit_api_client
from src.adapters.cli.main import app
from src.application.services.stockbit_session import StockbitSession
from src.application.use_case.sync_macro_calendar_use_case import SyncMacroCalendarResponse

runner = CliRunner()


def _mock_authenticated_session(monkeypatch):
    fake_client = object.__new__(_stockbit_api_client.StockbitApiClient)
    monkeypatch.setattr(
        macro_commands,
        "get_stockbit_session",
        lambda stockbit_config=None: StockbitSession(api_client=fake_client, authenticated=True),
    )


def _mock_unauthenticated_session(monkeypatch):
    monkeypatch.setattr(macro_commands, "get_stockbit_session", lambda stockbit_config=None: None)


class FakeUseCase:
    def __init__(self, response: SyncMacroCalendarResponse) -> None:
        self._response = response
        self.execute_calls: list = []

    def execute(self, request):
        self.execute_calls.append(request)
        return self._response


def _wire_fake_use_case(monkeypatch, response: SyncMacroCalendarResponse) -> FakeUseCase:
    fake_uc = FakeUseCase(response)
    monkeypatch.setattr(
        macro_commands,
        "SyncMacroCalendarUseCase",
        lambda provider, repository: fake_uc,
    )
    monkeypatch.setattr(
        macro_commands,
        "StockbitMacroCalendarProvider",
        lambda api_client, stockbit_config=None: object(),
    )
    monkeypatch.setattr(macro_commands, "SQLiteMacroCalendarRepository", lambda db_path: object())
    return fake_uc


def _response(**overrides) -> SyncMacroCalendarResponse:
    kwargs = dict(
        status="success",
        fetched_count=2,
        stored_count=2,
        category_counts={"bi_rate": 1, "other": 1},
        errors=(),
        from_cache=False,
    )
    kwargs.update(overrides)
    return SyncMacroCalendarResponse(**kwargs)


class TestNotAuthenticated:
    def test_no_session_exits_1(self, monkeypatch, tmp_path: Path):
        _mock_unauthenticated_session(monkeypatch)
        result = runner.invoke(app, ["fetch", "macro-calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 1
        assert "Not authenticated." in result.stdout + (result.stderr or "")


class TestSuccessAndFailure:
    def test_success_prints_counts(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        fake = _wire_fake_use_case(monkeypatch, _response())
        result = runner.invoke(app, ["fetch", "macro-calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 0
        assert "Macro calendar sync: success" in result.stdout
        assert "bi_rate: 1" in result.stdout
        assert "Stored 2 events" in result.stdout
        assert fake.execute_calls[0].force_remote_fetch is False

    def test_refresh_sets_force(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        fake = _wire_fake_use_case(monkeypatch, _response())
        result = runner.invoke(
            app, ["fetch", "macro-calendar", "--refresh", "--db", str(tmp_path / "x.db")]
        )
        assert result.exit_code == 0
        assert fake.execute_calls[0].force_remote_fetch is True

    def test_cached_message(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        _wire_fake_use_case(
            monkeypatch,
            _response(status="cached", from_cache=True, fetched_count=0, stored_count=0),
        )
        result = runner.invoke(app, ["fetch", "macro-calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 0
        assert "Already synced today" in result.stdout

    def test_failed_exits_1(self, monkeypatch, tmp_path: Path):
        _mock_authenticated_session(monkeypatch)
        _wire_fake_use_case(
            monkeypatch,
            _response(
                status="failed",
                fetched_count=0,
                stored_count=0,
                category_counts={},
                errors=("auth-or-network",),
            ),
        )
        result = runner.invoke(app, ["fetch", "macro-calendar", "--db", str(tmp_path / "x.db")])
        assert result.exit_code == 1
        assert "failed" in (result.stdout + (result.stderr or "")).lower()
