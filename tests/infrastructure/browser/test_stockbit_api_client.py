"""
Tests for StockbitApiClient.

Mocking strategy:
- token_store is a real StockbitTokenStore pointing at tmp_path
- token_refresher is a simple lambda
- httpx.get is monkeypatched to return fake responses
"""

import base64
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.browser.stockbit_api_client import (
    StockbitApiClient,
    StockbitSessionExpired,
)
from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore

# ── Helpers ────────────────────────────────────────────────────────────────

_counter = 0


def _make_jwt(exp_offset_hours: float = 4.0) -> str:
    """Each call produces a unique token regardless of timing."""
    global _counter
    _counter += 1
    import json as _json

    payload = {"sub": f"user-{_counter}", "exp": int(time.time() + exp_offset_hours * 3600)}
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(_json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fakesig"


def _make_store(tmp_path: Path, token: str | None = None) -> StockbitTokenStore:
    store = StockbitTokenStore(tmp_path / "token.json")
    if token is not None:
        store.save(token)
    return store


def _fake_response(status: int = 200, body: dict | None = None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body or {"data": "ok"}
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


# ── Happy path ─────────────────────────────────────────────────────────────


def test_get_with_valid_cached_token(tmp_path):
    token = _make_jwt()
    store = _make_store(tmp_path, token)
    refresher_called = []
    client = StockbitApiClient(store, lambda: refresher_called.append(1) or "newtoken")

    with patch("httpx.get", return_value=_fake_response(200, {"result": "data"})) as mock_get:
        result = client.get("https://exodus.stockbit.com/test")

    assert result == {"result": "data"}
    assert len(refresher_called) == 0, "refresher must not be called when cached token is valid"
    assert mock_get.call_args[1]["headers"]["Authorization"] == f"Bearer {token}"


def test_get_sends_browser_compatible_headers(tmp_path):
    token = _make_jwt()
    client = StockbitApiClient(_make_store(tmp_path, token), lambda: None)

    with patch("httpx.get", return_value=_fake_response()) as mock_get:
        client.get("https://exodus.stockbit.com/test")

    headers = mock_get.call_args.kwargs["headers"]
    assert headers["user-agent"].startswith("Mozilla/5.0")
    assert "Chrome/" in headers["user-agent"]
    assert headers["accept-language"] == "en-US,en;q=0.9,id;q=0.8"
    assert headers["origin"] == "https://stockbit.com"
    assert headers["referer"] == "https://stockbit.com/"


def test_get_without_cached_token_triggers_refresh(tmp_path):
    store = _make_store(tmp_path, None)  # no stored token
    fresh_token = _make_jwt()
    client = StockbitApiClient(store, lambda: fresh_token)

    with patch("httpx.get", return_value=_fake_response(200, {"ok": True})):
        result = client.get("https://exodus.stockbit.com/test")

    assert result == {"ok": True}
    assert store.load() == fresh_token  # token persisted after refresh


# ── 401 refresh flow ───────────────────────────────────────────────────────


def test_get_401_triggers_single_refresh_then_retries(tmp_path):
    old_token = _make_jwt()
    new_token = _make_jwt()
    store = _make_store(tmp_path, old_token)
    refresh_count = [0]

    def refresher():
        refresh_count[0] += 1
        return new_token

    client = StockbitApiClient(store, refresher)

    call_count = [0]

    def fake_get(url, **kwargs):
        call_count[0] += 1
        token_used = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
        if token_used == old_token:
            return _fake_response(401)
        return _fake_response(200, {"refreshed": True})

    with patch("httpx.get", side_effect=fake_get):
        result = client.get("https://exodus.stockbit.com/test")

    assert result == {"refreshed": True}
    assert refresh_count[0] == 1, "exactly one refresh on 401"
    assert call_count[0] == 2, "two GET calls: original + retry"


def test_get_401_after_refresh_raises_session_expired(tmp_path):
    """If the refreshed token also gets 401, auth is typed — not silent None."""
    token = _make_jwt()
    store = _make_store(tmp_path, token)
    client = StockbitApiClient(store, lambda: _make_jwt())

    with patch("httpx.get", return_value=_fake_response(401)):
        with pytest.raises(StockbitSessionExpired):
            client.get("https://exodus.stockbit.com/test")


# ── Refresh failure ────────────────────────────────────────────────────────


def test_get_no_token_and_refresher_returns_none(tmp_path):
    store = _make_store(tmp_path, None)
    client = StockbitApiClient(store, lambda: None)

    with pytest.raises(StockbitSessionExpired):
        client.get("https://exodus.stockbit.com/test")


def test_get_401_and_refresher_returns_none(tmp_path):
    token = _make_jwt()
    store = _make_store(tmp_path, token)
    client = StockbitApiClient(store, lambda: None)

    with patch("httpx.get", return_value=_fake_response(401)):
        with pytest.raises(StockbitSessionExpired):
            client.get("https://exodus.stockbit.com/test")


def test_get_rejects_hs256_refresh_without_persisting_or_requesting(tmp_path):
    store = _make_store(tmp_path)
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": int(time.time() + 3600)}).encode())
        .rstrip(b"=")
        .decode()
    )
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    client = StockbitApiClient(store, lambda: f"{header}.{payload}.signature")

    with patch("httpx.get") as mock_get:
        with pytest.raises(StockbitSessionExpired):
            client.get("https://exodus.stockbit.com/test")

    assert store.load() is None
    mock_get.assert_not_called()


def test_get_rejects_malformed_rs256_refresh_without_persisting_or_requesting(tmp_path):
    store = _make_store(tmp_path)
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    client = StockbitApiClient(store, lambda: f"{header}.not-valid-base64.signature")

    with patch("httpx.get") as mock_get:
        with pytest.raises(StockbitSessionExpired):
            client.get("https://exodus.stockbit.com/test")

    assert store.load() is None
    mock_get.assert_not_called()


# ── Network errors ─────────────────────────────────────────────────────────


def test_get_network_error_returns_none(tmp_path):
    token = _make_jwt()
    store = _make_store(tmp_path, token)
    client = StockbitApiClient(store, lambda: None)

    with patch("httpx.get", side_effect=Exception("connection refused")):
        result = client.get("https://exodus.stockbit.com/test")

    assert result is None


def test_get_network_error_does_not_call_refresher(tmp_path):
    token = _make_jwt()
    store = _make_store(tmp_path, token)
    refresh_count = []
    client = StockbitApiClient(store, lambda: (refresh_count.append(1), None)[1])

    with patch("httpx.get", side_effect=Exception("connection refused")):
        result = client.get("https://exodus.stockbit.com/test")

    assert result is None
    assert len(refresh_count) == 0, "refresher must not be called on a network error"


def test_get_locally_expired_token_triggers_exactly_one_refresh(tmp_path):
    expired_token = _make_jwt(exp_offset_hours=-1.0)
    f = tmp_path / "token.json"
    f.write_text(
        json.dumps(
            {
                "token": expired_token,
                "fetched_at": "2020-01-01T00:00:00+00:00",
                "exp": int(time.time() - 3600),
            }
        )
    )
    store = StockbitTokenStore(f)

    fresh_token = _make_jwt()
    refresh_count = [0]

    def refresher():
        refresh_count[0] += 1
        return fresh_token

    client = StockbitApiClient(store, refresher)

    with patch("httpx.get", return_value=_fake_response(200, {"result": "fresh-data"})) as mock_get:
        result = client.get("https://exodus.stockbit.com/test")

    assert refresh_count[0] == 1, "exactly one refresh when locally-stored token is expired"
    assert result == {"result": "fresh-data"}
    assert mock_get.call_args[1]["headers"]["Authorization"] == f"Bearer {fresh_token}"
    assert store.load() == fresh_token


# ── No infinite refresh loop ───────────────────────────────────────────────


def test_no_infinite_refresh_loop(tmp_path):
    """A single get() call must trigger at most one browser refresh."""
    store = _make_store(tmp_path, None)
    refresh_count = [0]

    def refresher():
        refresh_count[0] += 1
        return _make_jwt()  # returns valid token each time

    client = StockbitApiClient(store, refresher)

    with patch("httpx.get", return_value=_fake_response(401)):
        with pytest.raises(StockbitSessionExpired):
            client.get("https://exodus.stockbit.com/test")

    assert refresh_count[0] <= 1, "at most one browser launch per get() call"


# ── Params passthrough ─────────────────────────────────────────────────────


def test_get_passes_params_to_httpx(tmp_path):
    token = _make_jwt()
    store = _make_store(tmp_path, token)
    client = StockbitApiClient(store, lambda: None)

    with patch("httpx.get", return_value=_fake_response(200, {})) as mock_get:
        client.get("https://exodus.stockbit.com/test", params={"limit": 10, "page": 1})

    assert mock_get.call_args[1]["params"] == {"limit": 10, "page": 1}
