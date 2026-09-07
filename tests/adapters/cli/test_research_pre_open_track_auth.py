"""Pre-open track uses StockbitAuthPort.ensure_usable and fail-closes on AuthFailure."""

from __future__ import annotations

import inspect
from datetime import datetime
from types import SimpleNamespace

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.application.fakes.stockbit_auth import FakeStockbitAuth
from src.application.ports.stockbit_auth import (
    StockbitAuthFailure,
    StockbitAuthFailureKind,
    StockbitAuthReady,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import AssessmentPurpose

runner = CliRunner()
_AUTH_FACTORY = "src.infrastructure.composition.stockbit_auth_factory.create_stockbit_auth_port"
_REPO = (
    "src.infrastructure.persistence.sqlite_learning_artifact_repository"
    ".SQLiteLearningArtifactRepository"
)


def _observation(*, ticker: str = "BBCA", day: datetime | None = None) -> SimpleNamespace:
    cutoff = day or datetime(2026, 6, 12, 8, 57, tzinfo=IDX_TIMEZONE)
    return SimpleNamespace(
        observation_id=f"obs-{ticker}",
        cutoff_at=cutoff,
        decision_payload={"ticker": ticker},
    )


class _Repo:
    def __init__(self, db_path) -> None:
        self.db_path = db_path

    def list_observations(self, purpose: AssessmentPurpose):
        assert purpose is AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
        return [_observation()]


def test_track_uses_auth_port_not_legacy_session_factory() -> None:
    from src.adapters.cli import research_pre_open_track_commands as mod

    source = inspect.getsource(mod.track)
    assert "ensure_usable" in source
    assert "create_stockbit_auth_port" in source
    assert "get_stockbit_session" not in source


def test_track_auth_failure_fails_closed_without_live_fetch(monkeypatch) -> None:
    fake = FakeStockbitAuth(
        ensure_result=StockbitAuthFailure(
            kind=StockbitAuthFailureKind.REFRESH_FAILED,
            message="headless capture failed",
        )
    )
    monkeypatch.setattr(_AUTH_FACTORY, lambda **_kwargs: fake)
    monkeypatch.setattr(_REPO, _Repo)

    opened = {"use_case": 0}

    def _boom(*_args, **_kwargs):
        opened["use_case"] += 1
        raise AssertionError("OpeningTrackUseCase must not run on AuthFailure")

    monkeypatch.setattr(
        "src.application.use_case.opening_track_use_case.OpeningTrackUseCase",
        _boom,
    )

    result = runner.invoke(
        app,
        ["research", "pre-open", "track", "--force", "--date", "2026-06-12", "BBCA"],
    )
    combined = result.stdout + result.stderr

    assert result.exit_code == 2, combined
    assert fake.ensure_calls == 1
    assert "Error [data_unavailable]:" in combined
    assert "headless capture failed" in combined
    assert "reauth --mode headed" in combined
    assert "eyJ" not in combined
    assert opened["use_case"] == 0


def test_track_auth_ready_proceeds_without_live_market(monkeypatch) -> None:
    fake = FakeStockbitAuth(ensure_result=StockbitAuthReady())
    monkeypatch.setattr(_AUTH_FACTORY, lambda **_kwargs: fake)
    monkeypatch.setattr(_REPO, _Repo)
    monkeypatch.setattr(
        "src.infrastructure.browser.stockbit_api_client.create_stockbit_api_client",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        "src.infrastructure.browser.playwright_stockbit_provider.PlaywrightStockbitProvider",
        lambda **_kwargs: object(),
    )

    class _UseCase:
        def __init__(self, **_kwargs) -> None:
            pass

        def execute(self, request):
            assert request.force is True
            assert "BBCA" in request.observation_ids_by_ticker
            return []

    monkeypatch.setattr(
        "src.application.use_case.opening_track_use_case.OpeningTrackUseCase",
        _UseCase,
    )

    result = runner.invoke(
        app,
        ["research", "pre-open", "track", "--force", "--date", "2026-06-12", "BBCA"],
    )
    combined = result.stdout + result.stderr

    assert result.exit_code == 0, combined
    assert fake.ensure_calls == 1
    assert "Tracking 1 tickers" in combined
    assert "Force mode" in combined
