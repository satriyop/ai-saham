"""
CLI tests for `saham fetch stockbit status`.

Follows the CliRunner + monkeypatch convention from test_fetch_calendar_commands.py:
the `status()` command body does `from ...playwright_stockbit_provider import
get_stockbit_session_status` as a local import inside the function, re-imported
fresh on every call, so we patch the name on the *source* module
(src.infrastructure.browser.playwright_stockbit_provider) rather than on the
adapter module.
"""

from __future__ import annotations

from typer.testing import CliRunner

import src.infrastructure.browser.playwright_stockbit_provider as playwright_stockbit_provider
from src.adapters.cli.main import app
from src.application.services.stockbit_session import StockbitSessionStatus

runner = CliRunner()


def _status(**overrides) -> StockbitSessionStatus:
    kwargs = dict(
        profile_exists=True,
        profile_path="/fake/.stockbit_profile",
        browser_login_age_hours=1.5,
        token_exists=True,
        token_state="valid",
        token_expires_at="2026-07-12T00:00:00+00:00",
        token_seconds_remaining=3600,
        token_expiry_source="jwt_exp",
    )
    kwargs.update(overrides)
    return StockbitSessionStatus(**kwargs)


def test_status_valid_token_shows_state_and_no_jwt_leak(monkeypatch):
    monkeypatch.setattr(
        playwright_stockbit_provider,
        "get_stockbit_session_status",
        lambda: _status(token_state="valid"),
    )

    result = runner.invoke(app, ["fetch", "stockbit", "status"])

    assert result.exit_code == 0
    assert "Token state" in result.stdout
    assert "valid" in result.stdout
    assert "eyJ" not in result.stdout


def test_status_expired_token_shows_refresh_guidance_not_age_wording(monkeypatch):
    monkeypatch.setattr(
        playwright_stockbit_provider,
        "get_stockbit_session_status",
        lambda: _status(
            token_state="expired",
            token_expires_at="2020-01-01T00:00:00+00:00",
            token_seconds_remaining=0,
        ),
    )

    result = runner.invoke(app, ["fetch", "stockbit", "status"])

    assert result.exit_code == 0
    assert "Token state" in result.stdout
    assert "expired" in result.stdout
    combined = result.stdout.lower()
    assert "refresh automatically" in combined or "login" in combined
    assert "possibly expired" not in combined


def test_status_no_profile_prints_message_and_exits_cleanly(monkeypatch):
    monkeypatch.setattr(
        playwright_stockbit_provider,
        "get_stockbit_session_status",
        lambda: _status(
            profile_exists=False,
            browser_login_age_hours=None,
            token_exists=False,
            token_state="missing",
            token_expires_at=None,
            token_seconds_remaining=None,
            token_expiry_source=None,
        ),
    )

    result = runner.invoke(app, ["fetch", "stockbit", "status"])

    assert result.exit_code == 0
    assert "No browser profile found" in result.stdout
