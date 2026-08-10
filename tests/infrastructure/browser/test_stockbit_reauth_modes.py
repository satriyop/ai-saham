"""Unit tests for Stockbit reauth modes and Chromium lock ownership preservation."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest

import src.infrastructure.browser.stockbit_session_actions as session_mod
from src.infrastructure.browser.stockbit_session_actions import (
    HeadlessCaptureDiag,
    StockbitReauthResult,
    _classify_headless_capture,
    reauth_stockbit_session,
)
from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore


def _make_jwt(payload: dict, alg: str = "RS256") -> str:
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": alg, "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fakesignature"


def _future_ts(hours: float = 2.0) -> int:
    return int(time.time() + hours * 3600)


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


# ── Headless diagnostics + retry harden ───────────────────────────────────


def test_classify_headless_capture_reasons() -> None:
    ok = _classify_headless_capture(
        attempt=1,
        max_attempts=3,
        page_url="https://stockbit.com/orderbook",
        settle_ms=4000,
        token="eyJ",
        valid_rs256=True,
        algorithm="RS256",
        token_state="valid",
        logged_in=True,
        on_auth=False,
    )
    assert ok.reason == "ok_rs256"
    assert ok.valid_rs256 is True

    ambiguous = _classify_headless_capture(
        attempt=1,
        max_attempts=3,
        page_url="about:blank",
        settle_ms=4000,
        token="eyJ",
        valid_rs256=True,
        algorithm="RS256",
        token_state="valid",
        logged_in=False,
        on_auth=False,
    )
    assert ambiguous.reason == "ok_rs256_ambiguous_url"

    auth = _classify_headless_capture(
        attempt=1,
        max_attempts=3,
        page_url="https://stockbit.com/login",
        settle_ms=4000,
        token=None,
        valid_rs256=False,
        algorithm=None,
        token_state=None,
        logged_in=False,
        on_auth=True,
    )
    assert auth.reason == "auth_ui"

    missing = _classify_headless_capture(
        attempt=2,
        max_attempts=3,
        page_url="https://stockbit.com/orderbook",
        settle_ms=6000,
        token=None,
        valid_rs256=False,
        algorithm=None,
        token_state=None,
        logged_in=True,
        on_auth=False,
    )
    assert missing.reason == "no_token_intercepted"

    hs = _classify_headless_capture(
        attempt=1,
        max_attempts=3,
        page_url="https://stockbit.com/orderbook",
        settle_ms=4000,
        token="eyJ",
        valid_rs256=False,
        algorithm="HS256",
        token_state="valid",
        logged_in=True,
        on_auth=False,
    )
    assert hs.reason == "token_not_rs256(alg=HS256)"


def test_headless_diag_format_never_embeds_token() -> None:
    diag = HeadlessCaptureDiag(
        attempt=1,
        max_attempts=3,
        page_url="https://stockbit.com/orderbook",
        settle_ms=4000,
        token_present=True,
        algorithm="RS256",
        token_state="valid",
        valid_rs256=True,
        logged_in=True,
        on_auth=False,
        reason="ok_rs256",
    )
    blob = "\n".join(diag.format_lines())
    assert "RS256" in blob
    assert "eyJ" not in blob
    assert "Bearer" not in blob


class _FakeCtx:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.goto_calls: list[str] = []
        self.wait_ms: list[int] = []

    def goto(self, url: str, timeout=None, wait_until=None) -> None:
        self.goto_calls.append(url)
        self.url = url

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_ms.append(ms)


class _FakeSyncPlaywrightCM:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *_a: object) -> bool:
        return False


def _patch_headless_runtime(
    monkeypatch: pytest.MonkeyPatch,
    page: _FakePage,
    *,
    resolve_sequence: list[str | None],
) -> list[_FakeCtx]:
    """Wire playwright fakes and a sequenced token resolve for headless reauth."""
    contexts: list[_FakeCtx] = []

    def _playwright_factory():
        return _FakeSyncPlaywrightCM()

    monkeypatch.setattr(session_mod, "_require_playwright", lambda: _playwright_factory)
    monkeypatch.setattr(session_mod.time, "sleep", lambda _s: None)

    def _ctx(_pw: object, _profile: Path, *, headless: bool = True) -> tuple[_FakeCtx, _FakePage]:
        assert headless is True
        ctx = _FakeCtx()
        contexts.append(ctx)
        return ctx, page

    monkeypatch.setattr(session_mod, "_persistent_context", _ctx)
    monkeypatch.setattr(session_mod, "_intercept_token", lambda _page: [])
    calls = {"n": 0}

    def _resolve(_page: object, _box: list[str]) -> str | None:
        idx = min(calls["n"], len(resolve_sequence) - 1)
        calls["n"] += 1
        return resolve_sequence[idx]

    monkeypatch.setattr(session_mod, "_resolve_token", _resolve)
    return contexts


def test_headless_saves_rs256_even_when_url_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "marker").write_text("x")
    token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    page = _FakePage(url="about:blank")
    # Capture path sets URL via goto; simulate flaky end state by not staying logged-in-looking
    # after resolve: override url after capture by using a page that goto leaves non-stockbit.
    page.goto = lambda url, timeout=None, wait_until=None: setattr(
        page, "url", "chrome-error://chromewebdata/"
    )  # type: ignore[method-assign]
    _patch_headless_runtime(monkeypatch, page, resolve_sequence=[token])

    result = reauth_stockbit_session(profile_dir=profile, mode="headless")

    assert result.success is True
    assert result.token_saved is True
    assert result.mode == "headless"
    assert StockbitTokenStore(profile / "token.json").load() == token
    out = capsys.readouterr().out
    assert "ambiguous" in out.lower() or "OK" in out
    assert token not in out


def test_headless_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "marker").write_text("x")
    token = _make_jwt({"exp": _future_ts(3)}, alg="RS256")
    page = _FakePage(url="https://stockbit.com/orderbook")
    settles: list[int] = []

    def tracking_goto(url: str, timeout=None, wait_until=None) -> None:
        page.url = url
        page.goto_calls.append(url)

    def tracking_wait(ms: int) -> None:
        settles.append(ms)

    page.goto = tracking_goto  # type: ignore[method-assign]
    page.wait_for_timeout = tracking_wait  # type: ignore[method-assign]
    contexts = _patch_headless_runtime(monkeypatch, page, resolve_sequence=[None, token])

    result = reauth_stockbit_session(profile_dir=profile, mode="headless")

    assert result.success is True
    assert result.token_saved is True
    assert StockbitTokenStore(profile / "token.json").load() == token
    assert len(contexts) == 2  # failed attempt + success
    assert all(c.closed for c in contexts)
    # Second attempt uses base settle + extra
    assert len(settles) >= 2
    assert settles[1] > settles[0]
    out = capsys.readouterr().out
    assert "Attempt 1/" in out
    assert "Attempt 2/" in out
    assert "no_token_intercepted" in out
    assert "Retrying" in out
    assert token not in out


def test_headless_fails_after_retries_with_diag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "marker").write_text("x")
    page = _FakePage(url="https://stockbit.com/orderbook")
    contexts = _patch_headless_runtime(monkeypatch, page, resolve_sequence=[None])

    result = reauth_stockbit_session(profile_dir=profile, mode="headless")

    assert result.success is False
    assert result.token_saved is False
    assert len(contexts) == session_mod._HEADLESS_MAX_ATTEMPTS
    assert not (profile / "token.json").exists()
    out = capsys.readouterr().out
    assert f"after {session_mod._HEADLESS_MAX_ATTEMPTS} attempt" in out
    assert "no_token_intercepted" in out or "no Exodus Bearer" in out
    assert "headed" in out.lower()
    assert "Last url=" in out


def test_headless_auth_ui_fails_closed_without_login_clicks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "marker").write_text("x")
    page = _FakePage(url="https://stockbit.com/login")

    def stay_on_login(url: str, timeout=None, wait_until=None) -> None:
        page.goto_calls.append(url)
        page.url = "https://stockbit.com/login"

    page.goto = stay_on_login  # type: ignore[method-assign]
    _patch_headless_runtime(monkeypatch, page, resolve_sequence=[None])
    clicks = {"n": 0}

    def _clicks(_p: object) -> tuple[str, ...]:
        clicks["n"] += 1
        return ("login",)

    monkeypatch.setattr(session_mod, "attempt_stockbit_reauth_clicks", _clicks)

    result = reauth_stockbit_session(profile_dir=profile, mode="headless")

    assert result.success is False
    assert clicks["n"] == 0
    assert "auth" in result.message.lower() or "headed" in result.message.lower()
