"""Regression: StockbitBrokerProvider.is_authenticated must not use login-marker age.

ADR-036 and StockbitSessionStatus treat browser_login_age_hours as informational
only. An expired JWT with a refreshable browser profile must still count as an
available Stockbit session so `saham fetch market` can lazy-refresh on API call
instead of hard-failing with STOCKBIT_SESSION_REQUIRED_ERROR.
"""

from __future__ import annotations

import time
from pathlib import Path

from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider


class _FakeApiClient:
    def get(self, url, params=None):
        return None


def _provider(profile_dir: Path) -> StockbitBrokerProvider:
    return StockbitBrokerProvider(api_client=_FakeApiClient(), profile_dir=profile_dir)


def test_is_authenticated_false_when_profile_missing(tmp_path):
    missing = tmp_path / "no-profile"
    assert _provider(missing).is_authenticated() is False


def test_is_authenticated_true_with_old_logged_in_at_marker(tmp_path):
    (tmp_path / ".logged_in_at").write_text(str(time.time() - 100 * 3600))
    assert _provider(tmp_path).is_authenticated() is True


def test_is_authenticated_true_with_expired_token_json_only(tmp_path):
    (tmp_path / "token.json").write_text("{}")
    assert _provider(tmp_path).is_authenticated() is True


def test_is_authenticated_true_with_chromium_default_profile_only(tmp_path):
    (tmp_path / "Default").mkdir()
    assert _provider(tmp_path).is_authenticated() is True


def test_is_authenticated_false_for_empty_profile_dir(tmp_path):
    assert _provider(tmp_path).is_authenticated() is False
