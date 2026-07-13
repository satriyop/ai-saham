"""
Tests for `_fallback_id` — the deterministic SHA-256 fallback used when a
Stockbit calendar row has no usable source id.

Must NOT use Python's non-deterministic `hash()`: same input always yields
the same 64-char lowercase hex digest, verified against a hand-computed
hashlib.sha256(...).hexdigest() of the same composite string the function
builds internally.
"""

import hashlib
import json

from src.infrastructure.browser.stockbit_corporate_action_event_parsers import (
    _fallback_id,
)


class TestFallbackIdDeterminism:
    def test_same_input_twice_yields_identical_digest(self):
        first = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 1})
        second = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 1})
        assert first == second

    def test_output_is_64_char_lowercase_hex(self):
        digest = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 1})
        assert len(digest) == 64
        assert digest == digest.lower()
        int(digest, 16)  # raises ValueError if not valid hex

    def test_matches_hand_computed_sha256(self):
        event_type, ticker, dates, raw = (
            "dividend",
            "BBCA",
            ["2026-07-15", "2026-07-10"],
            {"b": 2, "a": 1},
        )
        expected_composite = (
            f"{event_type}|{ticker}|"
            f"{'|'.join(sorted(d for d in dates if d))}|"
            f"{json.dumps(raw, sort_keys=True, default=str)}"
        )
        expected = hashlib.sha256(expected_composite.encode("utf-8")).hexdigest()
        assert _fallback_id(event_type, ticker, dates, raw) == expected

    def test_different_ticker_yields_different_digest(self):
        a = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 1})
        b = _fallback_id("dividend", "BBRI", ["2026-07-15"], {"a": 1})
        assert a != b

    def test_different_date_yields_different_digest(self):
        a = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 1})
        b = _fallback_id("dividend", "BBCA", ["2026-08-01"], {"a": 1})
        assert a != b

    def test_different_raw_dict_yields_different_digest(self):
        a = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 1})
        b = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 2})
        assert a != b

    def test_dates_in_different_order_yield_same_hash(self):
        """Dates are sorted internally before hashing."""
        a = _fallback_id("dividend", "BBCA", ["2026-07-15", "2026-01-01"], {"a": 1})
        b = _fallback_id("dividend", "BBCA", ["2026-01-01", "2026-07-15"], {"a": 1})
        assert a == b

    def test_empty_string_dates_are_filtered_before_hashing(self):
        a = _fallback_id("dividend", "BBCA", ["2026-07-15", ""], {"a": 1})
        b = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 1})
        assert a == b

    def test_raw_dict_key_order_does_not_affect_hash(self):
        """json.dumps(..., sort_keys=True) makes key order irrelevant."""
        a = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"a": 1, "b": 2})
        b = _fallback_id("dividend", "BBCA", ["2026-07-15"], {"b": 2, "a": 1})
        assert a == b
