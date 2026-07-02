import base64
import json
import os
import stat
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_jwt(payload: dict) -> str:
    """Construct a minimal RS256-shaped JWT with a fake signature."""
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fakesignature"


def _future_ts(hours: float = 2.0) -> int:
    return int(time.time() + hours * 3600)


def _past_ts(hours: float = 2.0) -> int:
    return int(time.time() - hours * 3600)


# ── load() ─────────────────────────────────────────────────────────────────


def test_load_missing_file(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    assert store.load() is None


def test_load_corrupt_json(tmp_path):
    f = tmp_path / "token.json"
    f.write_text("not valid json {{{")
    store = StockbitTokenStore(f)
    assert store.load() is None


def test_load_missing_token_key(tmp_path):
    f = tmp_path / "token.json"
    f.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat()}))
    store = StockbitTokenStore(f)
    assert store.load() is None


def test_load_valid_exp_claim(tmp_path):
    token = _make_jwt({"sub": "user", "exp": _future_ts(2)})
    store = StockbitTokenStore(tmp_path / "token.json")
    store.save(token)
    assert store.load() == token


def test_load_expired_exp_claim(tmp_path):
    token = _make_jwt({"sub": "user", "exp": _past_ts(1)})
    f = tmp_path / "token.json"
    f.write_text(json.dumps({
        "token": token,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "exp": _past_ts(1),
    }))
    store = StockbitTokenStore(f)
    assert store.load() is None


def test_load_exp_within_skew_margin(tmp_path):
    # Token expires in 30s — within the 60s skew → should be treated as expired
    token = _make_jwt({"exp": int(time.time()) + 30})
    f = tmp_path / "token.json"
    f.write_text(json.dumps({
        "token": token,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "exp": int(time.time()) + 30,
    }))
    store = StockbitTokenStore(f)
    assert store.load() is None


def test_load_no_exp_fresh_fetched_at(tmp_path):
    # No exp claim, fetched 1 hour ago, TTL = 8h → valid
    token = _make_jwt({"sub": "user"})  # no exp
    fetched_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    f = tmp_path / "token.json"
    f.write_text(json.dumps({"token": token, "fetched_at": fetched_at, "exp": None}))
    store = StockbitTokenStore(f, ttl_hours=8.0)
    assert store.load() == token


def test_load_no_exp_stale_fetched_at(tmp_path):
    # No exp claim, fetched 9 hours ago, TTL = 8h → expired
    token = _make_jwt({"sub": "user"})
    fetched_at = (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
    f = tmp_path / "token.json"
    f.write_text(json.dumps({"token": token, "fetched_at": fetched_at, "exp": None}))
    store = StockbitTokenStore(f, ttl_hours=8.0)
    assert store.load() is None


def test_load_no_fetched_at_no_exp(tmp_path):
    f = tmp_path / "token.json"
    f.write_text(json.dumps({"token": "sometoken", "exp": None}))
    store = StockbitTokenStore(f)
    assert store.load() is None


# ── save() ─────────────────────────────────────────────────────────────────


def test_save_round_trip(tmp_path):
    token = _make_jwt({"exp": _future_ts(4)})
    store = StockbitTokenStore(tmp_path / "token.json")
    store.save(token)
    assert store.load() == token


def test_save_creates_parent_dirs(tmp_path):
    store = StockbitTokenStore(tmp_path / "sub" / "dir" / "token.json")
    token = _make_jwt({"exp": _future_ts(4)})
    store.save(token)
    assert (tmp_path / "sub" / "dir" / "token.json").exists()


def test_save_chmod_0600(tmp_path):
    token = _make_jwt({"exp": _future_ts(4)})
    f = tmp_path / "token.json"
    store = StockbitTokenStore(f)
    store.save(token)
    mode = oct(stat.S_IMODE(os.stat(f).st_mode))
    assert mode == "0o600"


def test_save_overwrites_expired_token(tmp_path):
    f = tmp_path / "token.json"
    store = StockbitTokenStore(f)
    old_token = _make_jwt({"exp": _past_ts(1)})
    store.save(old_token)
    new_token = _make_jwt({"exp": _future_ts(4)})
    store.save(new_token)
    assert store.load() == new_token


# ── clear() ────────────────────────────────────────────────────────────────


def test_clear_removes_file(tmp_path):
    token = _make_jwt({"exp": _future_ts(4)})
    store = StockbitTokenStore(tmp_path / "token.json")
    store.save(token)
    store.clear()
    assert store.load() is None


def test_clear_on_missing_file_is_safe(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    store.clear()  # should not raise


# ── _decode_exp() ──────────────────────────────────────────────────────────


def test_decode_exp_valid():
    exp = _future_ts(4)
    token = _make_jwt({"exp": exp})
    assert StockbitTokenStore._decode_exp(token) == exp


def test_decode_exp_missing_claim():
    token = _make_jwt({"sub": "user"})
    assert StockbitTokenStore._decode_exp(token) is None


def test_decode_exp_invalid_token():
    assert StockbitTokenStore._decode_exp("notajwt") is None
    assert StockbitTokenStore._decode_exp("a.b") is None
    assert StockbitTokenStore._decode_exp("") is None
