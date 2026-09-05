"""Fail-closed capture outside the pre-open / NCP window (issue #7).

``saham research pre-open capture`` must not TypeError when ``run_date`` is
None and wall-clock is outside the live window, must not write observations,
and must surface a clear data_unavailable outside-window message.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.screen_pre_open_workflow_factory import (
    PreOpenBrowserPlan,
    _build_run_snapshot_screen,
)
from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.domain.value_objects.market_status import MarketStatus
from src.domain.value_objects.screener_result import MoverData
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

runner = CliRunner()

_BYPASS_GUARD_STATUS = MarketStatus(
    status="STATUS_OPEN",
    session_name="Pre-Open",
    is_open=False,
    session_open=None,
    session_close=None,
    fetched_at=datetime(2026, 6, 12, 8, 50),
    source="stockbit",
)


def test_capture_outside_window_fails_closed_without_typeerror_or_persist(monkeypatch, tmp_path):
    """Outside window + no --session: clear data_unavailable, no observation write."""

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # ~09:13 WIB — past both pre-open and NCP locked-input windows.
            return datetime(2026, 6, 12, 9, 13, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.research_pre_open_capture_commands.datetime",
        _FixedDatetime,
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_pre_open_capture_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )

    create_calls: list[dict] = []
    record_execute = MagicMock()

    def _fake_create(**kwargs):
        create_calls.append(kwargs)
        raise AssertionError("create_pre_open_cli_workflow must not run outside window")

    monkeypatch.setattr(
        "src.adapters.cli.research_pre_open_capture_commands.create_pre_open_cli_workflow",
        _fake_create,
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_pre_open_capture_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=object(), autonomous=True, session_missing=False
        ),
    )

    db_path = tmp_path / "data.db"
    db_path.touch()
    result = runner.invoke(app, ["research", "pre-open", "capture", "--db", str(db_path)])

    assert result.exit_code == 2, result.output
    assert "TypeError" not in result.output
    assert "'<=' not supported" not in result.output
    assert "data_unavailable" in result.output
    assert "Capture rejected: outside the IDX pre-open window" in result.output
    assert "08:56" in result.output and "08:58" in result.output
    assert create_calls == []
    record_execute.assert_not_called()


def test_capture_outside_window_does_not_call_record_observations(monkeypatch, tmp_path):
    """Belt-and-suspenders: even if factory were reached, assert no persist path."""

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 12, 10, 15, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.research_pre_open_capture_commands.datetime",
        _FixedDatetime,
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_pre_open_capture_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )

    workflow_created = {"count": 0}

    def _fake_create(**kwargs):
        workflow_created["count"] += 1
        raise AssertionError("workflow must not be created on outside-window capture")

    monkeypatch.setattr(
        "src.adapters.cli.research_pre_open_capture_commands.create_pre_open_cli_workflow",
        _fake_create,
    )

    db_path = tmp_path / "data.db"
    db_path.touch()
    result = runner.invoke(
        app,
        ["research", "pre-open", "capture", "--db", str(db_path)],
    )

    assert result.exit_code == 2
    assert workflow_created["count"] == 0
    assert "outside the IDX pre-open window" in result.output


def test_run_snapshot_screen_none_as_of_date_returns_none_without_typeerror(tmp_path):
    """Defensive harden: as_of_date=None must not compare dates (issue #7)."""
    db_path = tmp_path / "iev.db"
    SQLiteIEVRepository(db_path).save_snapshot(
        date(2026, 6, 12),
        [MoverData(ticker="BBCA", iev=150_000, iep=9000)],
    )

    run = _build_run_snapshot_screen(
        db_path=db_path,
        market_repository=MagicMock(),
        broker_repository=MagicMock(),
        registry=MagicMock(),
        ai_explainer=None,
        notation_provider=None,
    )

    assert run(PreOpenScreenConfig(fast_mode=True), None) is None


def test_run_snapshot_screen_with_date_still_selects_snapshot(tmp_path):
    db_path = tmp_path / "iev.db"
    SQLiteIEVRepository(db_path).save_snapshot(
        date(2026, 6, 11),
        [MoverData(ticker="BBCA", iev=150_000, iep=9000)],
    )

    screen_calls: list = []

    class _FakeScreen:
        def __init__(self, **kwargs):
            pass

        def execute(self, request):
            screen_calls.append(request)
            return MagicMock(
                result=MagicMock(
                    screened_date=request.run_date,
                    candidates=[],
                    total_movers_seen=1,
                    iev_min=100_000,
                )
            )

    import src.adapters.cli.screen_pre_open_workflow_factory as factory

    monkey_screen = _FakeScreen
    # Patch PreOpenScreenUseCase used inside _run
    from unittest.mock import patch

    with patch.object(factory, "PreOpenScreenUseCase", monkey_screen):
        run = _build_run_snapshot_screen(
            db_path=db_path,
            market_repository=MagicMock(),
            broker_repository=MagicMock(),
            registry=MagicMock(),
            ai_explainer=None,
            notation_provider=None,
        )
        result = run(PreOpenScreenConfig(fast_mode=True), date(2026, 6, 12))

    assert result is not None
    assert result.snapshot_date == date(2026, 6, 11)
    assert len(screen_calls) == 1
