"""
CLI commands for Stockbit browser session management.

Commands:
  saham fetch stockbit login   — create persistent browser session profile
  saham fetch stockbit reauth  — JWT refresh (headless default) or headed UI recovery
  saham fetch stockbit status  — check session health without opening a browser
  saham fetch stockbit browse  — open a headed browser with the saved profile

Layer: Adapter
"""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from src.adapters.cli.cli_errors import raise_data_unavailable, raise_user_error
from src.adapters.cli.fetch_stockbit_playwright_guard import require_playwright_cli


def login(
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout", help="Seconds to wait for manual login (use 300+ if you have 2FA)", min=30
        ),
    ] = 300,
) -> None:
    """
    Open a browser window for manual Stockbit login. Saves browser profile.

    The browser stays open until you log in or the timeout expires.
    The persistent profile (.stockbit_profile/) is reused by all subsequent commands.

    Examples:
        saham fetch stockbit login
        saham fetch stockbit login --timeout 180
    """
    require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit_provider import save_stockbit_session

    try:
        save_stockbit_session(timeout=timeout)
    except Exception as e:
        raise_data_unavailable(f"Login failed: {e}")


def reauth(
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout",
            help="Seconds to wait after auto-clicks if still on login UI (headed only)",
            min=30,
        ),
    ] = 180,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help=(
                "headless: JWT refresh from cookies only (cron default). "
                "headed: visible browser + Login/OK clicks + optional human finish."
            ),
        ),
    ] = "headless",
) -> None:
    """
    Refresh Exodus JWT from the saved Stockbit browser profile.

    Default ``--mode headless`` opens no window: cookies/session mint a JWT or
    the command fails closed (for cron). Use ``--mode headed`` when login UI
    recovery is needed (password autofill / manual clicks).

    Requires a profile from ``saham fetch stockbit login`` at least once.

    Examples:
        saham fetch stockbit reauth
        saham fetch stockbit reauth --mode headless
        saham fetch stockbit reauth --mode headed --timeout 120
    """
    require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit_provider import reauth_stockbit_session

    normalized = (mode or "").strip().lower()
    if normalized not in ("headless", "headed"):
        raise_user_error(f"Invalid --mode {mode!r}; expected 'headless' or 'headed'.")

    try:
        result = reauth_stockbit_session(
            timeout=timeout,
            mode=normalized,  # type: ignore[arg-type]
        )
    except Exception as e:
        raise_data_unavailable(
            f"Reauth failed: {e}",
            tip="Run: saham fetch stockbit login",
        )
    if not result.success:
        raise_data_unavailable(
            "Reauth failed.",
            tip="Run: saham fetch stockbit login",
        )


def status() -> None:
    """
    Check the health of the saved Stockbit session without opening a browser.

    Shows browser-profile age (informational only) and the Exodus API JWT's
    local validity separately. This is a local, read-only assessment — it
    does not prove Stockbit has accepted the token; only a live API call can.

    Example:
        saham fetch stockbit status
    """
    from src.infrastructure.browser.playwright_stockbit_provider import get_stockbit_session_status

    info = get_stockbit_session_status()

    typer.echo("")
    typer.echo("Stockbit Session Status")
    typer.echo("=" * 40)

    if not info.profile_exists:
        typer.echo(typer.style("  No browser profile found.", fg=typer.colors.RED))
        typer.echo(f"  Expected profile: {info.profile_path}")
        typer.echo("")
        typer.echo("Run: saham fetch stockbit login")
        return

    typer.echo("  Type            : persistent browser profile")
    typer.echo(f"  Profile dir     : {info.profile_path}")

    if info.browser_login_age_hours is not None:
        typer.echo(
            f"  Browser login   : {info.browser_login_age_hours:.1f}h ago (informational only)"
        )
    else:
        typer.echo("  Browser login   : unknown (no .logged_in_at marker)")

    state_colors = {
        "valid": typer.colors.GREEN,
        "expired": typer.colors.YELLOW,
        "missing": typer.colors.YELLOW,
        "invalid": typer.colors.RED,
    }
    typer.echo(
        "  Token state     : "
        + typer.style(info.token_state, fg=state_colors.get(info.token_state, typer.colors.WHITE))
    )
    if info.token_expires_at:
        typer.echo(
            f"  Token expires   : {info.token_expires_at}  (source: {info.token_expiry_source})"
        )
    if info.token_state == "valid" and info.token_seconds_remaining is not None:
        typer.echo(f"  Token remaining : {info.token_seconds_remaining // 60} min")

    typer.echo("")
    if info.token_state == "valid":
        typer.echo("Next: saham fetch stockbit spy  (discover API endpoints)")
        typer.echo("      saham fetch stockbit test (live smoke-test)")
    else:
        typer.echo(
            "Token is not locally valid. Try:\n"
            "  saham fetch stockbit reauth              # headless JWT refresh\n"
            "  saham fetch stockbit reauth --mode headed  # UI recovery\n"
            "  saham fetch stockbit login               # first-time profile only"
        )


def browse(
    url: Annotated[
        Optional[str],
        typer.Option("--url", "-u", help="Stockbit page to open"),
    ] = None,
) -> None:
    """
    Open a headed browser with the saved profile and keep it open for browsing.

    Uses the persistent profile (.stockbit_profile/). The browser stays open
    until you press Ctrl+C.

    Examples:
        saham fetch stockbit browse
        saham fetch stockbit browse --url https://stockbit.com/stocks/BBCA
    """
    require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit_provider import browse_stockbit_session

    target = url or "https://stockbit.com/stream"
    try:
        browse_stockbit_session(url=target)
    except Exception as e:
        raise_data_unavailable(str(e), tip="Run: saham fetch stockbit login")
