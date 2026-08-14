"""StockbitAuthAdapter — port behavior with fake store/refresher, no Playwright."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from src.application.ports.stockbit_auth import (
    StockbitAuthFailure,
    StockbitAuthFailureKind,
    StockbitAuthPort,
    StockbitAuthReady,
    StockbitAuthRefreshMode,
)
from src.infrastructure.browser.stockbit_auth_adapter import StockbitAuthAdapter
from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore


def _jwt(exp_hours: float = 4.0, alg: str = "RS256") -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": alg}).encode()).rstrip(b"=").decode()
    body = (
        base64.urlsafe_b64encode(json.dumps({"exp": int(time.time() + exp_hours * 3600)}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{body}.sig"


def _profile(tmp_path: Path) -> Path:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / ".gitkeep").write_text("x")
    return profile


def test_adapter_is_stockbit_auth_port(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    adapter = StockbitAuthAdapter(profile, StockbitTokenStore(profile / "token.json"))
    assert isinstance(adapter, StockbitAuthPort)


def test_ensure_usable_valid_token_does_not_refresh(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = StockbitTokenStore(profile / "token.json")
    store.save(_jwt())
    calls: list[StockbitAuthRefreshMode] = []

    def refresh(mode: StockbitAuthRefreshMode) -> StockbitAuthReady:
        calls.append(mode)
        return StockbitAuthReady()

    adapter = StockbitAuthAdapter(profile, store, refresh=refresh)
    result = adapter.ensure_usable()
    assert isinstance(result, StockbitAuthReady)
    assert calls == []


def test_ensure_usable_missing_profile_without_refresh(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    calls: list[StockbitAuthRefreshMode] = []
    adapter = StockbitAuthAdapter(
        missing,
        StockbitTokenStore(missing / "token.json"),
        refresh=lambda m: calls.append(m) or StockbitAuthReady(),
    )
    result = adapter.ensure_usable()
    assert isinstance(result, StockbitAuthFailure)
    assert result.kind is StockbitAuthFailureKind.MISSING_PROFILE
    assert "eyJ" not in result.message
    assert calls == []


def test_ensure_usable_missing_token_refreshes_headless_once(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = StockbitTokenStore(profile / "token.json")
    calls: list[StockbitAuthRefreshMode] = []

    def refresh(mode: StockbitAuthRefreshMode) -> StockbitAuthReady:
        calls.append(mode)
        store.save(_jwt())
        return StockbitAuthReady()

    adapter = StockbitAuthAdapter(profile, store, refresh=refresh)
    result = adapter.ensure_usable()
    assert isinstance(result, StockbitAuthReady)
    assert calls == [StockbitAuthRefreshMode.HEADLESS]


def test_ensure_usable_refresh_failure_is_typed(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = StockbitTokenStore(profile / "token.json")
    fail = StockbitAuthFailure(
        kind=StockbitAuthFailureKind.REFRESH_FAILED,
        message="headless capture failed",
    )
    adapter = StockbitAuthAdapter(profile, store, refresh=lambda _m: fail)
    result = adapter.ensure_usable()
    assert result == fail


def test_force_refresh_headed_uses_injected_strategy(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = StockbitTokenStore(profile / "token.json")
    modes: list[StockbitAuthRefreshMode] = []

    def refresh(mode: StockbitAuthRefreshMode) -> StockbitAuthFailure:
        modes.append(mode)
        return StockbitAuthFailure(kind=StockbitAuthFailureKind.AUTH_UI, message="need headed")

    adapter = StockbitAuthAdapter(profile, store, refresh=refresh)
    result = adapter.force_refresh(StockbitAuthRefreshMode.HEADED)
    assert isinstance(result, StockbitAuthFailure)
    assert result.kind is StockbitAuthFailureKind.AUTH_UI
    assert modes == [StockbitAuthRefreshMode.HEADED]


def test_default_refresh_maps_auth_ui_message(tmp_path: Path, monkeypatch) -> None:
    from src.infrastructure.browser import stockbit_auth_adapter as adapter_mod
    from src.infrastructure.browser.stockbit_session_actions import StockbitReauthResult

    profile = _profile(tmp_path)
    store = StockbitTokenStore(profile / "token.json")

    def fake_reauth(**_kwargs: object) -> StockbitReauthResult:
        return StockbitReauthResult(
            success=False,
            token_saved=False,
            already_authenticated=False,
            auto_clicks=(),
            message="Headless JWT refresh failed (auth UI). Run headed.",
            mode="headless",
        )

    monkeypatch.setattr(adapter_mod, "reauth_stockbit_session", fake_reauth)
    adapter = StockbitAuthAdapter(profile, store)
    result = adapter.force_refresh(StockbitAuthRefreshMode.HEADLESS)
    assert isinstance(result, StockbitAuthFailure)
    assert result.kind is StockbitAuthFailureKind.AUTH_UI


def test_default_refresh_success_without_stored_jwt_is_failure(tmp_path: Path, monkeypatch) -> None:
    from src.infrastructure.browser import stockbit_auth_adapter as adapter_mod
    from src.infrastructure.browser.stockbit_session_actions import StockbitReauthResult

    profile = _profile(tmp_path)
    store = StockbitTokenStore(profile / "token.json")

    def fake_reauth(**_kwargs: object) -> StockbitReauthResult:
        return StockbitReauthResult(
            success=True,
            token_saved=False,
            already_authenticated=True,
            auto_clicks=(),
            message="profile marked logged-in",
            mode="headed",
        )

    monkeypatch.setattr(adapter_mod, "reauth_stockbit_session", fake_reauth)
    adapter = StockbitAuthAdapter(profile, store)
    result = adapter.force_refresh(StockbitAuthRefreshMode.HEADED)
    assert isinstance(result, StockbitAuthFailure)
    assert result.kind is StockbitAuthFailureKind.REFRESH_FAILED


def test_inspect_reports_store_without_jwt(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    store = StockbitTokenStore(profile / "token.json")
    token = _jwt()
    store.save(token)
    adapter = StockbitAuthAdapter(profile, store, refresh=lambda _m: StockbitAuthReady())
    status = adapter.inspect()
    assert status.profile_exists is True
    assert status.token_exists is True
    assert status.token_state == "valid"
    blob = repr(status)
    assert token not in blob
    assert "eyJ" not in blob
