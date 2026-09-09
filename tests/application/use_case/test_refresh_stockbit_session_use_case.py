"""RefreshStockbitSessionUseCase must not succeed unless status is a usable RS256 JWT."""

from __future__ import annotations

from src.application.fakes.stockbit_auth import FakeStockbitAuth
from src.application.ports.stockbit_auth import (
    StockbitAuthFailure,
    StockbitAuthFailureKind,
    StockbitAuthReady,
    StockbitAuthRefreshMode,
)
from src.application.services.stockbit_session import (
    StockbitSessionStatus,
    status_shows_usable_rs256,
)
from src.application.use_case.refresh_stockbit_session_use_case import (
    RefreshStockbitSessionRequest,
    RefreshStockbitSessionUseCase,
)


def _status(**overrides: object) -> StockbitSessionStatus:
    payload = {
        "profile_exists": True,
        "profile_path": ".stockbit_profile",
        "browser_login_age_hours": 1.0,
        "token_exists": True,
        "token_state": "valid",
        "token_expires_at": "2026-09-09T12:00:00+00:00",
        "token_seconds_remaining": 3600,
        "token_expiry_source": "jwt_exp",
    }
    payload.update(overrides)
    return StockbitSessionStatus(**payload)  # type: ignore[arg-type]


def test_status_shows_usable_rs256_only_when_valid_token_exists() -> None:
    assert status_shows_usable_rs256(_status(token_state="valid")) is True
    assert status_shows_usable_rs256(_status(token_state="expired")) is False
    assert status_shows_usable_rs256(_status(token_state="invalid")) is False
    assert status_shows_usable_rs256(_status(token_exists=False, token_state="missing")) is False


def test_refresh_ready_requires_inspect_usable_rs256() -> None:
    auth = FakeStockbitAuth(
        refresh_results={StockbitAuthRefreshMode.HEADLESS: StockbitAuthReady()},
        status=_status(token_state="valid"),
    )
    result = RefreshStockbitSessionUseCase(auth).execute(
        RefreshStockbitSessionRequest(mode=StockbitAuthRefreshMode.HEADLESS)
    )
    assert result.ready is True
    assert result.failure is None
    assert auth.refresh_calls == [StockbitAuthRefreshMode.HEADLESS]
    assert result.status.token_state == "valid"


def test_refresh_ready_from_port_is_failure_when_status_expired() -> None:
    auth = FakeStockbitAuth(
        refresh_results={StockbitAuthRefreshMode.HEADLESS: StockbitAuthReady()},
        status=_status(
            token_state="expired",
            token_expires_at="2026-09-09T00:34:55+00:00",
            token_seconds_remaining=0,
        ),
    )
    result = RefreshStockbitSessionUseCase(auth).execute(
        RefreshStockbitSessionRequest(mode=StockbitAuthRefreshMode.HEADLESS)
    )
    assert result.ready is False
    assert result.failure is not None
    assert result.failure.kind is StockbitAuthFailureKind.EXPIRED
    assert "usable RS256" in result.failure.message
    assert "eyJ" not in result.failure.message
    assert "Bearer" not in result.failure.message


def test_refresh_ready_from_port_is_failure_when_status_missing() -> None:
    auth = FakeStockbitAuth(
        refresh_results={StockbitAuthRefreshMode.HEADLESS: StockbitAuthReady()},
        status=_status(token_exists=False, token_state="missing"),
    )
    result = RefreshStockbitSessionUseCase(auth).execute(
        RefreshStockbitSessionRequest(mode=StockbitAuthRefreshMode.HEADLESS)
    )
    assert result.ready is False
    assert result.failure is not None
    assert result.failure.kind is StockbitAuthFailureKind.MISSING_TOKEN


def test_refresh_propagates_port_failure_even_if_status_looks_valid() -> None:
    failure = StockbitAuthFailure(
        kind=StockbitAuthFailureKind.AUTH_UI,
        message="headless cannot complete login UI",
    )
    auth = FakeStockbitAuth(
        refresh_results={StockbitAuthRefreshMode.HEADLESS: failure},
        status=_status(token_state="valid"),
    )
    result = RefreshStockbitSessionUseCase(auth).execute(
        RefreshStockbitSessionRequest(mode=StockbitAuthRefreshMode.HEADLESS)
    )
    assert result.ready is False
    assert result.failure == failure
