"""
Tests for save_stockbit_session / browse_stockbit_session / get_stockbit_session_status
and the pure helper _persist_newer_token in stockbit_session_actions.py.

All Playwright interaction is faked — no real browser is ever launched.
"""

from __future__ import annotations

import base64
import json
import time

import src.infrastructure.browser.stockbit_session_actions as browser_mod
from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore

# ── Helpers ───────────────────────────────────────────────────────────────


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


def _past_ts(hours: float = 1.0) -> int:
    return int(time.time() - hours * 3600)


# ── Fake Playwright plumbing ─────────────────────────────────────────────


class _FakeCtx:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakePage:
    def __init__(self, login_succeeds: bool = True):
        self.url = "https://stockbit.com/login"
        self._login_succeeds = login_succeeds
        self.goto_calls: list[str] = []

    def goto(self, url, timeout=None, wait_until=None):
        self.goto_calls.append(url)
        if self._login_succeeds:
            self.url = url

    def wait_for_url(self, predicate, timeout=None):
        if not self._login_succeeds:
            raise Exception("Timeout 30000ms exceeded")
        self.url = "https://stockbit.com/stream"

    def wait_for_timeout(self, ms):
        pass


class _FakeSyncPlaywrightCM:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


def _fake_sync_playwright():
    return _FakeSyncPlaywrightCM()


class _FakeBrowsePage:
    """Page fake for browse_stockbit_session's `while True` loop.

    Raises KeyboardInterrupt after a configurable number of wait_for_timeout
    ticks so the loop terminates deterministically.
    """

    def __init__(self, max_ticks: int = 3):
        self.tick = 0
        self._max_ticks = max_ticks
        self.goto_calls: list[str] = []

    def goto(self, url, timeout=None, wait_until=None):
        self.goto_calls.append(url)

    def wait_for_timeout(self, ms):
        self.tick += 1
        if self.tick > self._max_ticks:
            raise KeyboardInterrupt()


def _patch_common(monkeypatch, fake_page, login_succeeds=True):
    monkeypatch.setattr(browser_mod, "_require_playwright", lambda: _fake_sync_playwright)
    fake_ctx = _FakeCtx()
    monkeypatch.setattr(
        browser_mod,
        "_persistent_context",
        lambda pw, profile_dir, headless=False: (fake_ctx, fake_page),
    )
    monkeypatch.setattr(browser_mod, "_intercept_token", lambda page: [])
    return fake_ctx


# ── _persist_newer_token (pure function) ────────────────────────────────


def test_persist_newer_token_no_growth_is_noop(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    token_box: list[str] = ["sometoken"]

    result = browser_mod._persist_newer_token(store, token_box, last_seen=1)

    assert result == 1
    assert not (tmp_path / "token.json").exists()


def test_persist_newer_token_saves_new_valid_rs256_token(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    token_box = [token]

    result = browser_mod._persist_newer_token(store, token_box, last_seen=0)

    assert result == 1
    assert store.load() == token


def test_persist_newer_token_repeated_call_without_growth_is_noop(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    token_box = [token]

    last_seen = browser_mod._persist_newer_token(store, token_box, last_seen=0)
    assert store.load() == token

    # Second call: token_box hasn't grown, last_seen already reflects it → no-op.
    result = browser_mod._persist_newer_token(store, token_box, last_seen=last_seen)

    assert result == last_seen
    assert store.load() == token


def test_persist_newer_token_older_exp_after_newer_saved_not_saved(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    newer_token = _make_jwt({"exp": _future_ts(4)}, alg="RS256")
    store.save(newer_token)

    older_token = _make_jwt({"exp": _future_ts(1)}, alg="RS256")
    token_box = [older_token]

    browser_mod._persist_newer_token(store, token_box, last_seen=0)

    assert store.load() == newer_token


def test_persist_newer_token_expired_candidate_not_saved(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    expired_token = _make_jwt({"exp": _past_ts(1)}, alg="RS256")
    token_box = [expired_token]

    browser_mod._persist_newer_token(store, token_box, last_seen=0)

    assert not (tmp_path / "token.json").exists()


def test_persist_newer_token_hs256_candidate_not_saved(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    hs256_token = _make_jwt({"exp": _future_ts(2)}, alg="HS256")
    token_box = [hs256_token]

    browser_mod._persist_newer_token(store, token_box, last_seen=0)

    assert not (tmp_path / "token.json").exists()


def test_persist_newer_token_empty_box_never_creates_file(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    token_box: list[str] = []

    result = browser_mod._persist_newer_token(store, token_box, last_seen=0)

    assert result == 0
    assert not (tmp_path / "token.json").exists()


# ── save_stockbit_session ────────────────────────────────────────────────


def test_save_session_login_succeeds_valid_token_saved(monkeypatch, tmp_path, capsys):
    fake_page = _FakePage(login_succeeds=True)
    _patch_common(monkeypatch, fake_page)
    token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    monkeypatch.setattr(browser_mod, "_resolve_token", lambda page, box: token)

    browser_mod.save_stockbit_session(profile_dir=tmp_path, timeout=5)

    assert (tmp_path / ".logged_in_at").exists()
    token_file = tmp_path / "token.json"
    assert token_file.exists()
    record = json.loads(token_file.read_text())
    assert record["token"] == token

    out = capsys.readouterr().out
    assert "captured and saved" in out.lower()
    assert token not in out


def test_save_session_login_succeeds_no_token_captured(monkeypatch, tmp_path, capsys):
    fake_page = _FakePage(login_succeeds=True)
    _patch_common(monkeypatch, fake_page)
    monkeypatch.setattr(browser_mod, "_resolve_token", lambda page, box: None)

    browser_mod.save_stockbit_session(profile_dir=tmp_path, timeout=5)

    assert (tmp_path / ".logged_in_at").exists()
    assert not (tmp_path / "token.json").exists()

    out = capsys.readouterr().out
    assert "could not capture" in out.lower()


def test_save_session_login_times_out(monkeypatch, tmp_path, capsys):
    fake_page = _FakePage(login_succeeds=False)
    _patch_common(monkeypatch, fake_page, login_succeeds=False)
    monkeypatch.setattr(browser_mod, "_resolve_token", lambda page, box: None)

    browser_mod.save_stockbit_session(profile_dir=tmp_path, timeout=5)

    assert not (tmp_path / ".logged_in_at").exists()
    assert not (tmp_path / "token.json").exists()

    out = capsys.readouterr().out
    assert "Timeout" in out
    assert "saved" not in out.lower() or "not saved" in out.lower()


def test_save_session_login_succeeds_hs256_token_rejected(monkeypatch, tmp_path, capsys):
    fake_page = _FakePage(login_succeeds=True)
    _patch_common(monkeypatch, fake_page)
    hs256_token = _make_jwt({"exp": _future_ts(2)}, alg="HS256")
    monkeypatch.setattr(browser_mod, "_resolve_token", lambda page, box: hs256_token)

    browser_mod.save_stockbit_session(profile_dir=tmp_path, timeout=5)

    assert (tmp_path / ".logged_in_at").exists()
    assert not (tmp_path / "token.json").exists()

    out = capsys.readouterr().out
    assert "could not capture" in out.lower()


# ── browse_stockbit_session ───────────────────────────────────────────────


def _setup_valid_session(tmp_path) -> str:
    """Write a valid RS256 token and a non-empty persistent browser profile."""
    token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    (tmp_path / ".gitkeep").write_text("x")  # non-empty profile dir
    StockbitTokenStore(tmp_path / "token.json").save(token)
    return token


def test_browse_session_proceeds_with_valid_token_ignores_logged_in_at(monkeypatch, tmp_path):
    _setup_valid_session(tmp_path)
    # Deliberately no .logged_in_at — browser profile contents are sufficient.
    fake_page = _FakeBrowsePage(max_ticks=1)
    _patch_common(monkeypatch, fake_page)

    browser_mod.browse_stockbit_session(profile_dir=tmp_path, url="https://stockbit.com/stream")

    assert not (tmp_path / ".logged_in_at").exists()


def test_browse_session_goto_alone_does_not_write_new_token(monkeypatch, tmp_path):
    existing = _setup_valid_session(tmp_path)
    fake_page = _FakeBrowsePage(max_ticks=1)
    _patch_common(monkeypatch, fake_page)

    browser_mod.browse_stockbit_session(profile_dir=tmp_path, url="https://stockbit.com/stream")

    assert fake_page.goto_calls == ["https://stockbit.com/stream"]
    # Token file still holds the same value — browse did not overwrite it.
    assert StockbitTokenStore(tmp_path / "token.json").load() == existing


def test_browse_session_flushes_token_when_first_wait_is_interrupted(monkeypatch, tmp_path):
    _setup_valid_session(tmp_path)
    fake_page = _FakeBrowsePage(max_ticks=0)
    fake_ctx = _patch_common(monkeypatch, fake_page)
    new_token = _make_jwt({"exp": _future_ts(4)}, alg="RS256")
    monkeypatch.setattr(browser_mod, "_intercept_token", lambda page: [new_token])

    browser_mod.browse_stockbit_session(profile_dir=tmp_path)

    assert StockbitTokenStore(tmp_path / "token.json").load() == new_token
    assert fake_ctx.closed is True


def test_browse_session_requires_existing_profile(tmp_path):
    try:
        browser_mod.browse_stockbit_session(profile_dir=tmp_path)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "stockbit login" in str(exc)


def test_browse_session_expired_token_does_not_force_login(monkeypatch, tmp_path):
    """Browser cookies may renew an expired API token during normal browsing."""
    expired_token = _make_jwt({"exp": _past_ts(1)}, alg="RS256")
    f = tmp_path / "token.json"
    f.write_text(
        json.dumps(
            {
                "token": expired_token,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                "exp": _past_ts(1),
            }
        )
    )
    (tmp_path / ".gitkeep").write_text("x")

    fresh_token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    monkeypatch.setattr(
        browser_mod,
        "save_stockbit_session",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("login must not run")),
    )
    fake_page = _FakeBrowsePage(max_ticks=1)
    _patch_common(monkeypatch, fake_page)
    monkeypatch.setattr(browser_mod, "_intercept_token", lambda page: [fresh_token])

    browser_mod.browse_stockbit_session(profile_dir=tmp_path)

    assert StockbitTokenStore(tmp_path / "token.json").load() == fresh_token
    assert fake_page.goto_calls == ["https://stockbit.com/stream"]


# ── get_stockbit_session_status ──────────────────────────────────────────


def test_get_session_status_old_marker_valid_token_age_does_not_affect_state(tmp_path):
    marker = tmp_path / ".logged_in_at"
    marker.write_text(str(time.time() - 100 * 3600))

    token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    StockbitTokenStore(tmp_path / "token.json").save(token)

    status = browser_mod.get_stockbit_session_status(profile_dir=tmp_path)

    assert status.browser_login_age_hours is not None
    assert status.browser_login_age_hours > 90
    assert status.token_state == "valid"


def test_get_session_status_old_marker_no_token(tmp_path):
    marker = tmp_path / ".logged_in_at"
    marker.write_text(str(time.time() - 100 * 3600))

    status = browser_mod.get_stockbit_session_status(profile_dir=tmp_path)

    assert status.token_exists is False
    assert status.token_state == "missing"
    assert status.profile_exists is True


def test_get_session_status_expired_stored_token(tmp_path):
    (tmp_path / ".logged_in_at").write_text(str(time.time()))
    f = tmp_path / "token.json"
    token = _make_jwt({"exp": _past_ts(1)}, alg="RS256")
    f.write_text(
        json.dumps(
            {
                "token": token,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                "exp": _past_ts(1),
            }
        )
    )

    status = browser_mod.get_stockbit_session_status(profile_dir=tmp_path)

    assert status.token_state == "expired"
    assert status.token_expires_at is not None


def test_get_session_status_performs_no_playwright_or_network_calls(tmp_path):
    # Deliberately no monkeypatching of _require_playwright/_persistent_context —
    # if this function touched Playwright, it would raise since playwright may
    # not even be installed/available in this environment.
    status = browser_mod.get_stockbit_session_status(profile_dir=tmp_path)

    assert status.profile_exists is False
    assert status.token_exists is False
    assert status.token_state == "missing"


def test_facade_compatibility():
    import src.infrastructure.browser.playwright_stockbit_browser as facade_mod
    import src.infrastructure.browser.stockbit_browser_context as context_mod
    import src.infrastructure.browser.stockbit_session_actions as session_mod
    import src.infrastructure.browser.stockbit_token_extractor as extractor_mod
    from src.infrastructure.browser.stockbit_api_client import StockbitSessionExpired

    assert facade_mod.save_stockbit_session is session_mod.save_stockbit_session
    assert facade_mod.browse_stockbit_session is session_mod.browse_stockbit_session
    assert facade_mod.spy_stockbit_session is session_mod.spy_stockbit_session
    assert facade_mod.get_stockbit_session_status is session_mod.get_stockbit_session_status
    assert facade_mod._persist_newer_token is session_mod._persist_newer_token

    assert facade_mod.DEFAULT_PROFILE_DIR is context_mod.DEFAULT_PROFILE_DIR
    assert facade_mod.BASE_URL is context_mod.BASE_URL
    assert facade_mod.STREAM_URL is context_mod.STREAM_URL
    assert facade_mod.SCREENER_URL is context_mod.SCREENER_URL
    assert facade_mod.ORDER_BOOK_URL is context_mod.ORDER_BOOK_URL
    assert facade_mod.ORDERBOOK_PAGE_URL is context_mod.ORDERBOOK_PAGE_URL
    assert facade_mod.LOGIN_URL is context_mod.LOGIN_URL
    assert facade_mod._require_playwright is context_mod._require_playwright
    assert facade_mod._persistent_context is context_mod._persistent_context

    assert facade_mod._intercept_token is extractor_mod._intercept_token
    assert facade_mod._resolve_token is extractor_mod._resolve_token
    assert facade_mod._extract_jwt is extractor_mod._extract_jwt
    assert facade_mod.extract_exodus_token is extractor_mod.extract_exodus_token

    assert facade_mod.StockbitSessionExpired is StockbitSessionExpired
