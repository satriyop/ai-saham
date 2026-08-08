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


def test_reauth_command_success_exit_zero(monkeypatch):
    from src.infrastructure.browser.stockbit_session_actions import StockbitReauthResult

    captured: dict = {}

    def _fake_reauth(timeout=180, mode="headless"):
        captured["timeout"] = timeout
        captured["mode"] = mode
        return StockbitReauthResult(
            success=True,
            token_saved=True,
            already_authenticated=True,
            auto_clicks=(),
            message="ok",
            mode=mode,
        )

    monkeypatch.setattr(
        playwright_stockbit_provider,
        "reauth_stockbit_session",
        _fake_reauth,
    )
    # CLI imports reauth from provider inside the function.
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_session_commands.require_playwright_cli",
        lambda: None,
    )

    result = runner.invoke(app, ["fetch", "stockbit", "reauth", "--timeout", "60"])

    assert result.exit_code == 0
    assert captured["mode"] == "headless"
    assert captured["timeout"] == 60


def test_reauth_command_failure_exit_one(monkeypatch):
    from src.infrastructure.browser.stockbit_session_actions import StockbitReauthResult

    monkeypatch.setattr(
        playwright_stockbit_provider,
        "reauth_stockbit_session",
        lambda timeout=180, mode="headless": StockbitReauthResult(
            success=False,
            token_saved=False,
            already_authenticated=False,
            auto_clicks=("login",),
            message="failed",
            mode=mode,
        ),
    )
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_session_commands.require_playwright_cli",
        lambda: None,
    )

    result = runner.invoke(app, ["fetch", "stockbit", "reauth"])

    assert result.exit_code == 2  # data_unavailable


def test_reauth_command_surfaces_profile_in_use_without_token_leak(monkeypatch):
    def _raise_profile_in_use(timeout=180, mode="headless"):
        raise RuntimeError("Failed to create a ProcessSingleton: profile is already in use")

    monkeypatch.setattr(
        playwright_stockbit_provider,
        "reauth_stockbit_session",
        _raise_profile_in_use,
    )
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_session_commands.require_playwright_cli",
        lambda: None,
    )

    result = runner.invoke(app, ["fetch", "stockbit", "reauth"])

    combined = result.stdout + result.stderr
    assert result.exit_code == 2  # data_unavailable
    assert "Reauth failed:" in combined
    assert "profile is already in use" in combined
    assert "eyJ" not in combined


def test_reauth_command_passes_headed_mode(monkeypatch):
    from src.infrastructure.browser.stockbit_session_actions import StockbitReauthResult

    captured: dict = {}

    def _fake_reauth(timeout=180, mode="headless"):
        captured["mode"] = mode
        return StockbitReauthResult(
            success=True,
            token_saved=True,
            already_authenticated=False,
            auto_clicks=("login",),
            message="ok",
            mode=mode,
        )

    monkeypatch.setattr(playwright_stockbit_provider, "reauth_stockbit_session", _fake_reauth)
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_session_commands.require_playwright_cli",
        lambda: None,
    )

    result = runner.invoke(
        app, ["fetch", "stockbit", "reauth", "--mode", "headed", "--timeout", "90"]
    )
    assert result.exit_code == 0
    assert captured["mode"] == "headed"


def test_reauth_command_rejects_invalid_mode(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_session_commands.require_playwright_cli",
        lambda: None,
    )
    result = runner.invoke(app, ["fetch", "stockbit", "reauth", "--mode", "turbo"])
    assert result.exit_code == 1
    assert "Invalid --mode" in (result.stdout + result.stderr)


def test_reauth_help_documents_mode_switch():
    result = runner.invoke(app, ["fetch", "stockbit", "reauth", "--help"])
    assert result.exit_code == 0
    out = result.stdout
    assert "--timeout" in out
    assert "--mode" in out
    assert "headless" in out
    assert "headed" in out
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


def test_test_command_exits_2_with_session_expired_message_when_unauthenticated(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_diagnostic_factory.get_stockbit_session",
        lambda stockbit_config=None: None,
    )

    result = runner.invoke(app, ["fetch", "stockbit", "test"])
    out = result.stdout + result.stderr

    assert result.exit_code == 2  # data_unavailable
    assert "Stockbit session expired. Run `saham fetch stockbit login` to refresh." in out
    assert "Error [data_unavailable]:" in out


def test_fetch_top5_command_exits_2_with_session_expired_message_when_unauthenticated(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.fetch_stockbit_diagnostic_factory.get_stockbit_session",
        lambda stockbit_config=None: None,
    )

    result = runner.invoke(app, ["fetch", "stockbit", "fetch-top5"])
    out = result.stdout + result.stderr

    assert result.exit_code == 2  # data_unavailable
    assert "Stockbit session expired. Run `saham fetch stockbit login` to refresh." in out
    assert "Error [data_unavailable]:" in out


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


def test_playwright_guard_exits_2_with_install_message_when_missing(monkeypatch, capsys):
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

    assert exc_info.value.exit_code == 2  # data_unavailable
    captured = capsys.readouterr()
    assert "playwright not installed." in captured.err
    assert "Run: pip install playwright && playwright install chromium" in captured.err
    assert "Error [data_unavailable]:" in captured.err
