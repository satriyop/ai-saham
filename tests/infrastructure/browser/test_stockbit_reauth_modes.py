"""Unit tests for Stockbit reauth modes and Chromium lock ownership preservation."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.infrastructure.browser.stockbit_session_actions as session_mod
from src.infrastructure.browser.stockbit_session_actions import (
    StockbitReauthResult,
    reauth_stockbit_session,
)


class _FakeSyncPlaywright:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *_args: object) -> bool:
        return False


def _profile_marker_snapshot(profile: Path) -> dict[str, tuple[str, str | bytes]]:
    snapshot: dict[str, tuple[str, str | bytes]] = {}
    for relative in (
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
        "RunningChromeVersion",
        "Default/Lock",
    ):
        path = profile / relative
        if path.is_symlink():
            snapshot[relative] = ("symlink", str(path.readlink()))
        elif path.is_dir():
            snapshot[relative] = ("directory", "")
        elif path.exists():
            snapshot[relative] = ("file", path.read_bytes())
    return snapshot


@pytest.mark.parametrize(
    ("marker_kind", "marker_value"),
    (
        ("symlink", "malformed-owner"),
        ("symlink", "host-99999999"),
        ("symlink", "remote-host-99999999"),
        ("file", ""),
        ("file", "host-99999999"),
        ("directory", ""),
    ),
)
def test_reauth_never_mutates_chromium_profile_markers_before_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    marker_kind: str,
    marker_value: str,
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    lock = profile / "SingletonLock"
    if marker_kind == "symlink":
        lock.symlink_to(marker_value)
    elif marker_kind == "directory":
        lock.mkdir()
    else:
        lock.write_text(marker_value)
    (profile / "Default").mkdir()
    (profile / "SingletonCookie").symlink_to("cookie")
    (profile / "SingletonSocket").symlink_to("socket")
    (profile / "RunningChromeVersion").symlink_to("1.0:1")
    (profile / "Default" / "Lock").write_bytes(b"default-lock")
    before = _profile_marker_snapshot(profile)

    monkeypatch.setattr(session_mod, "_require_playwright", lambda: _FakeSyncPlaywright)

    def fail_profile_launch(_pw: object, launched_profile: Path, *, headless: bool):
        assert launched_profile == profile
        assert headless is True
        assert _profile_marker_snapshot(profile) == before
        raise RuntimeError("Failed to create a ProcessSingleton: profile is already in use")

    monkeypatch.setattr(session_mod, "_persistent_context", fail_profile_launch)

    with pytest.raises(RuntimeError, match="ProcessSingleton"):
        reauth_stockbit_session(profile_dir=profile, mode="headless")

    assert _profile_marker_snapshot(profile) == before


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
