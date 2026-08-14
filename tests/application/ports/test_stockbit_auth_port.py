"""Contract tests for StockbitAuthPort — behavior through the port seam only.

Layer: Test
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from src.application.fakes.stockbit_auth import FakeStockbitAuth
from src.application.ports.stockbit_auth import (
    StockbitAuthFailure,
    StockbitAuthFailureKind,
    StockbitAuthPort,
    StockbitAuthReady,
    StockbitAuthRefreshMode,
)
from src.application.services.stockbit_session import StockbitSessionStatus


def _status(**overrides: object) -> StockbitSessionStatus:
    payload = {
        "profile_exists": True,
        "profile_path": ".stockbit_profile",
        "browser_login_age_hours": 1.0,
        "token_exists": True,
        "token_state": "valid",
        "token_expires_at": "2026-08-15T01:00:00+00:00",
        "token_seconds_remaining": 3600,
        "token_expiry_source": "jwt_exp",
    }
    payload.update(overrides)
    return StockbitSessionStatus(**payload)  # type: ignore[arg-type]


def test_fake_is_a_stockbit_auth_port() -> None:
    auth: StockbitAuthPort = FakeStockbitAuth()
    assert isinstance(auth, StockbitAuthPort)


def test_ensure_usable_ready() -> None:
    auth = FakeStockbitAuth(ensure_result=StockbitAuthReady())
    result = auth.ensure_usable()
    assert isinstance(result, StockbitAuthReady)


@pytest.mark.parametrize(
    "kind",
    (
        StockbitAuthFailureKind.MISSING_PROFILE,
        StockbitAuthFailureKind.MISSING_TOKEN,
        StockbitAuthFailureKind.INVALID_TOKEN,
        StockbitAuthFailureKind.EXPIRED,
        StockbitAuthFailureKind.REFRESH_FAILED,
        StockbitAuthFailureKind.AUTH_UI,
    ),
)
def test_ensure_usable_typed_failure(kind: StockbitAuthFailureKind) -> None:
    failure = StockbitAuthFailure(kind=kind, message=f"failed:{kind.value}")
    auth = FakeStockbitAuth(ensure_result=failure)
    result = auth.ensure_usable()
    assert isinstance(result, StockbitAuthFailure)
    assert result.kind is kind
    assert "eyJ" not in result.message
    assert not hasattr(result, "token")


def test_force_refresh_headless_and_headed_are_distinct() -> None:
    ready = StockbitAuthReady()
    headed_fail = StockbitAuthFailure(
        kind=StockbitAuthFailureKind.AUTH_UI,
        message="headless cannot complete login UI",
    )
    auth = FakeStockbitAuth(
        refresh_results={
            StockbitAuthRefreshMode.HEADLESS: ready,
            StockbitAuthRefreshMode.HEADED: headed_fail,
        }
    )
    assert isinstance(auth.force_refresh(StockbitAuthRefreshMode.HEADLESS), StockbitAuthReady)
    headed = auth.force_refresh(StockbitAuthRefreshMode.HEADED)
    assert isinstance(headed, StockbitAuthFailure)
    assert headed.kind is StockbitAuthFailureKind.AUTH_UI


def test_inspect_returns_status_without_jwt_material() -> None:
    status = _status()
    auth = FakeStockbitAuth(status=status)
    seen = auth.inspect()
    assert seen == status
    names = {f.name for f in fields(seen)}
    assert "token" not in names
    blob = repr(seen)
    assert "eyJ" not in blob
    assert "Bearer" not in blob
