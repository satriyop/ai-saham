import base64
import json
import os
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_jwt(payload: dict, alg: str = "RS256") -> str:
    """Construct a minimal JWT with a fake signature. Defaults to RS256-shaped header."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": alg, "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
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
    f.write_text(
        json.dumps(
            {
                "token": token,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "exp": _past_ts(1),
            }
        )
    )
    store = StockbitTokenStore(f)
    assert store.load() is None


def test_load_exp_within_skew_margin(tmp_path):
    # Token expires in 30s — within the 60s skew → should be treated as expired
    token = _make_jwt({"exp": int(time.time()) + 30})
    f = tmp_path / "token.json"
    f.write_text(
        json.dumps(
            {
                "token": token,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "exp": int(time.time()) + 30,
            }
        )
    )
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


# ── inspect() / describe_candidate() / is_worth_saving() ────────────────────


def test_inspect_future_exp_reports_valid_jwt_exp(tmp_path):
    token = _make_jwt({"exp": _future_ts(2)})
    store = StockbitTokenStore(tmp_path / "token.json")
    store.save(token)

    meta = store.inspect()

    assert meta.exists is True
    assert meta.state == "valid"
    assert meta.expiry_source == "jwt_exp"
    assert meta.algorithm == "RS256"
    assert isinstance(meta.expires_at, datetime)
    assert meta.expires_at.tzinfo is not None
    assert meta.seconds_remaining is not None and meta.seconds_remaining > 0


def test_describe_candidate_future_exp_reports_valid_jwt_exp(tmp_path):
    token = _make_jwt({"exp": _future_ts(2)})
    store = StockbitTokenStore(tmp_path / "token.json")

    meta = store.describe_candidate(token)

    assert meta.exists is True
    assert meta.state == "valid"
    assert meta.expiry_source == "jwt_exp"
    assert meta.algorithm == "RS256"
    assert isinstance(meta.expires_at, datetime)
    assert meta.expires_at.tzinfo is not None
    assert meta.seconds_remaining is not None and meta.seconds_remaining > 0


def test_inspect_past_exp_reports_expired(tmp_path):
    token = _make_jwt({"exp": _past_ts(1)})
    f = tmp_path / "token.json"
    f.write_text(
        json.dumps(
            {
                "token": token,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "exp": _past_ts(1),
            }
        )
    )
    store = StockbitTokenStore(f)

    meta = store.inspect()

    assert meta.state == "expired"


def test_inspect_exp_within_skew_window_reports_expired(tmp_path):
    # exp in 30s — inside the 60s skew — should be classified expired.
    token = _make_jwt({"exp": int(time.time()) + 30})
    f = tmp_path / "token.json"
    f.write_text(
        json.dumps(
            {
                "token": token,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "exp": int(time.time()) + 30,
            }
        )
    )
    store = StockbitTokenStore(f)

    meta = store.inspect()

    assert meta.state == "expired"


def test_inspect_no_exp_recent_fetched_at_reports_valid_fallback_ttl(tmp_path):
    token = _make_jwt({"sub": "user"})  # no exp claim
    fetched_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    f = tmp_path / "token.json"
    f.write_text(json.dumps({"token": token, "fetched_at": fetched_at, "exp": None}))
    store = StockbitTokenStore(f, ttl_hours=8.0)

    meta = store.inspect()

    assert meta.state == "valid"
    assert meta.expiry_source == "fallback_ttl"


def test_inspect_malformed_token_reports_invalid_even_with_recent_fetched_at(tmp_path):
    f = tmp_path / "token.json"
    f.write_text(
        json.dumps(
            {
                "token": "notajwt",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )
    store = StockbitTokenStore(f)

    meta = store.inspect()

    assert meta.state == "invalid"


def test_inspect_three_segment_token_with_malformed_payload_is_invalid(tmp_path):
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    token = f"{header}.not-valid-base64.signature"
    store = StockbitTokenStore(tmp_path / "token.json")

    meta = store.describe_candidate(token)

    assert meta.state == "invalid"
    assert store.is_worth_saving(token) is False


def test_load_rejects_malformed_token_even_with_future_stored_exp(tmp_path):
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    token = f"{header}.not-valid-base64.signature"
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps(
            {
                "token": token,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "exp": _future_ts(2),
            }
        )
    )

    assert StockbitTokenStore(path).load() is None


def test_inspect_non_object_payload_is_invalid(tmp_path):
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b"[]").rstrip(b"=").decode()
    token = f"{header}.{payload}.signature"

    assert StockbitTokenStore(tmp_path / "token.json").describe_candidate(token).state == "invalid"


def test_inspect_invalid_exp_type_is_invalid(tmp_path):
    token = _make_jwt({"exp": "not-a-timestamp"})

    assert StockbitTokenStore(tmp_path / "token.json").describe_candidate(token).state == "invalid"


def test_inspect_missing_file_reports_missing(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")

    meta = store.inspect()

    assert meta.exists is False
    assert meta.state == "missing"


def test_inspect_corrupt_json_reports_invalid(tmp_path):
    f = tmp_path / "token.json"
    f.write_text("not valid json {{{")
    store = StockbitTokenStore(f)

    meta = store.inspect()

    assert meta.exists is False
    assert meta.state == "invalid"


def test_metadata_never_carries_raw_token(tmp_path):
    token = _make_jwt({"exp": _future_ts(2)})
    store = StockbitTokenStore(tmp_path / "token.json")
    store.save(token)

    meta = store.inspect()

    assert not hasattr(meta, "token")
    assert token not in repr(meta)


def test_describe_candidate_recognizes_rs256_header():
    token = _make_jwt({"exp": int(time.time() + 3600)}, alg="RS256")
    store = StockbitTokenStore(Path("/nonexistent/token.json"))

    meta = store.describe_candidate(token)

    assert meta.algorithm == "RS256"


def test_is_worth_saving_rejects_hs256_even_when_store_empty(tmp_path):
    hs256_token = _make_jwt({"exp": int(time.time() + 3600)}, alg="HS256")
    store = StockbitTokenStore(tmp_path / "token.json")

    assert store.is_worth_saving(hs256_token) is False


def test_load_rejects_preexisting_hs256_token(tmp_path):
    token = _make_jwt({"exp": _future_ts(2)}, alg="HS256")
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps(
            {
                "token": token,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "exp": _future_ts(2),
            }
        )
    )

    store = StockbitTokenStore(path)

    assert store.inspect().state == "invalid"
    assert store.load() is None


def test_no_exp_fallback_accepts_legacy_naive_utc_fetched_at(tmp_path):
    token = _make_jwt({"sub": "user"}, alg="RS256")
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps(
            {
                "token": token,
                "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "exp": None,
            }
        )
    )

    assert StockbitTokenStore(path).load() == token


def test_is_worth_saving_accepts_candidate_with_later_exp_than_stored(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    stored_token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    store.save(stored_token)

    candidate = _make_jwt({"exp": _future_ts(4)}, alg="RS256")

    assert store.is_worth_saving(candidate) is True


def test_is_worth_saving_rejects_identical_token_already_stored(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    token = _make_jwt({"exp": _future_ts(2)}, alg="RS256")
    store.save(token)

    assert store.is_worth_saving(token) is False


def test_is_worth_saving_rejects_earlier_exp_than_stored(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    stored_token = _make_jwt({"exp": _future_ts(4)}, alg="RS256")
    store.save(stored_token)

    earlier_candidate = _make_jwt({"exp": _future_ts(1)}, alg="RS256")

    assert store.is_worth_saving(earlier_candidate) is False


def test_is_worth_saving_rejects_expired_candidate_regardless_of_stored_state(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    stored_token = _make_jwt({"exp": _future_ts(4)}, alg="RS256")
    store.save(stored_token)

    expired_candidate = _make_jwt({"exp": _past_ts(1)}, alg="RS256")
    assert store.is_worth_saving(expired_candidate) is False


def test_is_worth_saving_rejects_expired_candidate_when_store_empty(tmp_path):
    store = StockbitTokenStore(tmp_path / "token.json")
    expired_candidate = _make_jwt({"exp": _past_ts(1)}, alg="RS256")

    assert store.is_worth_saving(expired_candidate) is False
