"""Unit tests for Stockbit reauth headless/headed modes and lock cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.browser.stockbit_session_actions import (
    StockbitReauthResult,
    _clear_stale_chromium_profile_locks,
    reauth_stockbit_session,
)


def test_clear_stale_locks_removes_dead_pid_singleton(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "Default").mkdir()
    # Unreachable PID — treat as dead lock owner.
    (profile / "SingletonLock").symlink_to("host-99999999")
    (profile / "SingletonCookie").symlink_to("cookie")
    (profile / "RunningChromeVersion").symlink_to("1.0:1")
    (profile / "Default" / "Lock").write_text("")

    _clear_stale_chromium_profile_locks(profile)

    assert not (profile / "SingletonLock").exists()
    assert not (profile / "SingletonCookie").exists()
    assert not (profile / "RunningChromeVersion").exists()
    assert not (profile / "Default" / "Lock").exists()


def test_clear_stale_locks_keeps_live_pid_singleton(tmp_path: Path) -> None:
    import os

    profile = tmp_path / "profile"
    profile.mkdir()
    live_pid = os.getpid()
    (profile / "SingletonLock").symlink_to(f"host-{live_pid}")
    (profile / "token.json").write_text("{}")

    _clear_stale_chromium_profile_locks(profile)

    # SingletonLock targets "host-<pid>" (not a real path), so exists() is False
    # unless follow_symlinks=False — the symlink itself must remain.
    assert (profile / "SingletonLock").exists(follow_symlinks=False)
    assert (profile / "token.json").exists()


def test_reauth_rejects_unknown_mode(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "marker").write_text("x")
    with pytest.raises(ValueError, match="headless"):
        reauth_stockbit_session(profile_dir=profile, mode="turbo")  # type: ignore[arg-type]


def test_reauth_requires_profile(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(RuntimeError, match="No Stockbit profile"):
        reauth_stockbit_session(profile_dir=missing, mode="headless")


def test_reauth_result_carries_mode() -> None:
    result = StockbitReauthResult(
        success=True,
        token_saved=True,
        already_authenticated=True,
        auto_clicks=(),
        message="ok",
        mode="headless",
    )
    assert result.mode == "headless"
