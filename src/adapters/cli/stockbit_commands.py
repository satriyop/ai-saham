"""
CLI commands for Stockbit browser session management and adapter diagnostics.

Commands:
  saham stockbit login   — save browser session cookies (headed Chromium)
  saham stockbit status  — check session health without opening a browser
  saham stockbit spy     — capture all API traffic to identify real endpoints
  saham stockbit test    — smoke-test the live adapter with saved session

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

stockbit_app = typer.Typer(
    name="stockbit",
    help="Stockbit session management and adapter diagnostics",
    no_args_is_help=True,
)

DEFAULT_SESSION_FILE = Path("stockbit_session.json")
DEFAULT_SPY_OUTPUT = Path("journals/stockbit-spy.json")


def _require_playwright_cli() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError:
        typer.echo(
            "playwright not installed.\n"
            "Run: pip install playwright && playwright install chromium",
            err=True,
        )
        raise typer.Exit(1)


@stockbit_app.command("login")
def login(
    session: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to save session cookies"),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Seconds to wait for manual login (use 300+ if you have 2FA)", min=30),
    ] = 300,
) -> None:
    """
    Open a browser window for manual Stockbit login. Saves session cookies.

    The browser stays open until you log in or the timeout expires.
    Cookies are saved and reused by all subsequent Stockbit commands.

    Examples:
        saham stockbit login
        saham stockbit login --timeout 180
        saham stockbit login --session .my-session.json
    """
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit import save_stockbit_session

    resolved = session or DEFAULT_SESSION_FILE
    try:
        save_stockbit_session(session_file=resolved, timeout=timeout)
    except Exception as e:
        typer.echo(f"Login failed: {e}", err=True)
        raise typer.Exit(1)


@stockbit_app.command("status")
def status(
    session: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to session file"),
    ] = None,
) -> None:
    """
    Check the health of the saved Stockbit session without opening a browser.

    Shows cookie count, session age, and whether auth cookies are present.

    Example:
        saham stockbit status
    """
    from src.infrastructure.browser.playwright_stockbit import get_session_status

    resolved = session or DEFAULT_SESSION_FILE
    info = get_session_status(resolved)

    typer.echo("")
    typer.echo("Stockbit Session Status")
    typer.echo("=" * 40)

    if not info["exists"]:
        typer.echo(typer.style("  No session file found.", fg=typer.colors.RED))
        typer.echo(f"  Expected: {info['path']}")
        typer.echo("")
        typer.echo("Run: saham stockbit login")
        return

    typer.echo(f"  File            : {info['path']}")
    typer.echo(f"  Cookies         : {info['cookie_count']}")
    typer.echo(f"  Auth cookies    : {info['auth_cookie_count']}")
    typer.echo(f"  localStorage    : {info.get('local_storage_keys', '?')} keys")
    auth_ls = info.get("auth_local_storage_keys", [])
    if auth_ls:
        typer.echo(f"  Auth LS keys    : {', '.join(auth_ls)}")

    if info.get("age_hours") is not None:
        age = info["age_hours"]
        age_str = f"{age:.1f}h ago"
        if age > 24:
            age_color = typer.colors.YELLOW
            age_str += " (may need refresh)"
        else:
            age_color = typer.colors.GREEN
        typer.echo(f"  Saved      : " + typer.style(age_str, fg=age_color))

    valid = info.get("likely_valid", False)
    validity_str = "likely valid" if valid else "possibly expired — re-run login"
    validity_color = typer.colors.GREEN if valid else typer.colors.RED
    typer.echo("  Status     : " + typer.style(validity_str, fg=validity_color))

    typer.echo("")
    if not valid:
        typer.echo("Run: saham stockbit login")
    else:
        typer.echo("Next: saham stockbit spy  (discover API endpoints)")
        typer.echo("      saham stockbit test (live smoke-test)")


@stockbit_app.command("spy")
def spy(
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help="Page to spy on: 'screener' (movers) or 'orderbook'",
        ),
    ] = "screener",
    ticker: Annotated[
        str,
        typer.Option("--ticker", help="Ticker for orderbook target (e.g. BBCA)"),
    ] = "BBCA",
    output: Annotated[
        Optional[Path],
        typer.Option("--output", help="Path to save captured traffic JSON"),
    ] = None,
    wait: Annotated[
        int,
        typer.Option("--wait", help="Seconds to wait for SPA to settle", min=2),
    ] = 6,
    session: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to session file"),
    ] = None,
) -> None:
    """
    Capture all API traffic from a Stockbit page to identify real endpoints.

    Opens a headed browser (so you can interact if needed), navigates to
    the target page, and saves every JSON API response to a file.

    The output shows which URLs contain movers/orderbook data — share this
    output when reporting adapter issues so selectors can be calibrated.

    Examples:
        saham stockbit spy
        saham stockbit spy --target orderbook --ticker BBRI
        saham stockbit spy --wait 10 --output journals/my-capture.json
    """
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit import spy_stockbit_session

    resolved_session = session or DEFAULT_SESSION_FILE
    resolved_output = output or DEFAULT_SPY_OUTPUT

    typer.echo(f"Target  : {target}" + (f" ({ticker})" if target == "orderbook" else ""))
    typer.echo(f"Wait    : {wait}s")
    typer.echo(f"Output  : {resolved_output}")
    typer.echo("")

    try:
        result = spy_stockbit_session(
            session_file=resolved_session,
            target=target,
            ticker=ticker,
            output_file=resolved_output,
            settle_ms=wait * 1000,
        )
    except Exception as e:
        typer.echo(f"Spy failed: {e}", err=True)
        raise typer.Exit(1)

    typer.echo("")
    typer.echo("=" * 60)
    typer.echo("SPY RESULTS")
    typer.echo("=" * 60)
    typer.echo(f"Total responses captured : {result['total_responses']}")
    typer.echo(f"JSON responses           : {result['json_responses']}")
    typer.echo(f"Unique JSON URLs         : {len(result['unique_json_urls'])}")
    typer.echo("")

    if result["movers_candidates"]:
        typer.echo(typer.style("Possible MOVERS endpoints:", fg=typer.colors.GREEN))
        for url in result["movers_candidates"]:
            typer.echo(f"  ★ {url}")
    else:
        typer.echo(typer.style("No movers endpoint detected.", fg=typer.colors.YELLOW))
        typer.echo("  The endpoint may use an unexpected URL pattern.")

    typer.echo("")

    if result["orderbook_candidates"]:
        typer.echo(typer.style("Possible ORDERBOOK endpoints:", fg=typer.colors.GREEN))
        for url in result["orderbook_candidates"]:
            typer.echo(f"  ★ {url}")
    else:
        typer.echo(typer.style("No orderbook endpoint detected.", fg=typer.colors.YELLOW))

    typer.echo("")
    typer.echo("All unique JSON URLs captured:")
    for url in result["unique_json_urls"]:
        typer.echo(f"  {url}")

    typer.echo("")
    typer.echo(f"Full capture saved → {result['output_file']}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  1. Share the URLs above (or the JSON file) to calibrate the adapter")
    typer.echo("  2. Once endpoints are confirmed: saham stockbit test")


@stockbit_app.command("test")
def test(
    iev_min: Annotated[
        int,
        typer.Option("--iev-min", help="IEV threshold (default 1 = get everything)", min=1),
    ] = 1,
    ticker: Annotated[
        str,
        typer.Option("--ticker", help="Ticker for orderbook smoke test"),
    ] = "BBCA",
    session: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to session file"),
    ] = None,
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser headless"),
    ] = True,
) -> None:
    """
    Smoke-test the Stockbit adapter with the saved session.

    Runs a live fetch of movers and order book and prints raw results.
    Use this to verify the adapter works after calibrating from spy output.

    Examples:
        saham stockbit test
        saham stockbit test --no-headless    (see the browser)
        saham stockbit test --ticker BMRI
    """
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider

    resolved_session = session or DEFAULT_SESSION_FILE

    provider = PlaywrightStockbitProvider(
        session_file=resolved_session,
        headless=headless,
    )

    # ── Test 1: movers ────────────────────────────────────────────────────
    typer.echo("")
    typer.echo("Test 1: fetch_preopen_movers(iev_min=1)")
    typer.echo("-" * 45)

    try:
        movers = provider.fetch_preopen_movers(iev_min=iev_min)
        if movers:
            typer.echo(
                typer.style(f"  ✓ {len(movers)} movers returned", fg=typer.colors.GREEN)
            )
            typer.echo("")
            typer.echo(f"  {'TICKER':<8} {'IEV':>12}")
            typer.echo("  " + "-" * 22)
            for m in movers[:10]:
                typer.echo(f"  {m.ticker:<8} {m.iev:>12,}")
            if len(movers) > 10:
                typer.echo(f"  ... and {len(movers) - 10} more")
        else:
            typer.echo(typer.style("  ✗ 0 movers returned", fg=typer.colors.RED))
            typer.echo("")
            typer.echo("  Diagnosis:")
            typer.echo("    — API intercept: no URL matched movers patterns")
            typer.echo("    — DOM scrape:    no table rows found")
            typer.echo("    — Next step:     saham stockbit spy --target screener")
    except Exception as e:
        typer.echo(typer.style(f"  ✗ Error: {e}", fg=typer.colors.RED))

    # ── Test 2: order book ────────────────────────────────────────────────
    typer.echo("")
    typer.echo(f"Test 2: fetch_order_book_best_bid({ticker})")
    typer.echo("-" * 45)

    try:
        bid = provider.fetch_order_book_best_bid(ticker)
        if bid:
            typer.echo(
                typer.style(
                    f"  ✓ Best bid: price={bid.price:,}  volume={bid.volume:,} lots",
                    fg=typer.colors.GREEN,
                )
            )
        else:
            typer.echo(typer.style("  ✗ No bid returned", fg=typer.colors.RED))
            typer.echo("")
            typer.echo(f"  Next step: saham stockbit spy --target orderbook --ticker {ticker}")
    except Exception as e:
        typer.echo(typer.style(f"  ✗ Error: {e}", fg=typer.colors.RED))

    typer.echo("")
