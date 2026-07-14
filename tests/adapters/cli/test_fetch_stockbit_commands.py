"""
CLI tests for `saham fetch stockbit status`.

Follows the CliRunner + monkeypatch convention from test_fetch_calendar_commands.py:
the `status()` command body (now in fetch_stockbit_session_commands.py) does
`from ...playwright_stockbit_provider import get_stockbit_session_status` as a
local import inside the function, re-imported fresh on every call, so we patch
the name on the *source* module (src.infrastructure.browser.playwright_stockbit_provider)
rather than on the adapter module.
"""

from __future__ import annotations

import pytest
import typer
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


def test_stockbit_help_lists_all_commands():
    result = runner.invoke(app, ["fetch", "stockbit", "--help"])

    assert result.exit_code == 0
    for command_name in ("login", "status", "spy", "test", "browse", "fetch-top5"):
        assert command_name in result.stdout


def test_test_command_exits_1_with_session_expired_message_when_unauthenticated(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_diagnostic_factory.get_stockbit_session",
        lambda stockbit_config=None: None,
    )

    result = runner.invoke(app, ["fetch", "stockbit", "test"])

    assert result.exit_code == 1
    assert "Stockbit session expired. Run `saham fetch stockbit login` to refresh." in result.stdout


def test_fetch_top5_command_exits_1_with_session_expired_message_when_unauthenticated(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_diagnostic_factory.get_stockbit_session",
        lambda stockbit_config=None: None,
    )

    result = runner.invoke(app, ["fetch", "stockbit", "fetch-top5"])

    assert result.exit_code == 1
    assert "Stockbit session expired. Run `saham fetch stockbit login` to refresh." in result.stdout


def test_router_does_not_import_concrete_stockbit_infrastructure():
    import ast
    import inspect

    import src.adapters.cli.fetch_stockbit_commands as router_module

    source = inspect.getsource(router_module)
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert not any(m.startswith("src.infrastructure") for m in imported_modules)


def test_playwright_guard_exits_1_with_install_message_when_missing(monkeypatch, capsys):
    import builtins

    from src.adapters.cli.fetch_stockbit_playwright_guard import require_playwright_cli

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "playwright":
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(typer.Exit) as exc_info:
        require_playwright_cli()

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "playwright not installed." in captured.err
    assert "Run: pip install playwright && playwright install chromium" in captured.err
