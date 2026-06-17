"""
CLI commands for Stockbit browser session management and adapter diagnostics.

Commands:
  saham data stockbit login   — save browser session cookies (headed Chromium)
  saham data stockbit status  — check session health without opening a browser
  saham data stockbit spy     — capture all API traffic to identify real endpoints
  saham data stockbit test    — smoke-test the live adapter with saved session

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
        saham data stockbit login
        saham data stockbit login --timeout 180
        saham data stockbit login --session .my-session.json
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
        saham data stockbit status
    """
    from src.infrastructure.browser.playwright_stockbit import get_session_status

    resolved = session or DEFAULT_SESSION_FILE
    info = get_session_status(resolved)

    typer.echo("")
    typer.echo("Stockbit Session Status")
    typer.echo("=" * 40)

    if not info["exists"]:
        typer.echo(typer.style("  No session found.", fg=typer.colors.RED))
        typer.echo(f"  Expected profile: {info['path']}")
        typer.echo("")
        typer.echo("Run: saham data stockbit login")
        return

    session_type = info.get("type", "unknown")
    if session_type == "persistent_profile":
        typer.echo(f"  Type            : persistent browser profile (recommended)")
        typer.echo(f"  Profile dir     : {info['path']}")
    else:
        typer.echo(f"  Type            : legacy cookie file")
        typer.echo(f"  File            : {info['path']}")
        typer.echo(f"  Cookies         : {info.get('cookie_count', '?')}")
        typer.echo(f"  Auth cookies    : {info.get('auth_cookie_count', '?')}")
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
        typer.echo("Run: saham data stockbit login")
    else:
        typer.echo("Next: saham data stockbit spy  (discover API endpoints)")
        typer.echo("      saham data stockbit test (live smoke-test)")


@stockbit_app.command("spy")
def spy(
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help=(
                "Page to spy on: 'screener' (movers), 'orderbook', "
                "'stock' (named broker breakdown for a ticker), "
                "'broker-scan' (foreign top stocks universe scan)"
            ),
        ),
    ] = "screener",
    ticker: Annotated[
        str,
        typer.Option("--ticker", help="Ticker for orderbook/stock target (e.g. BBCA)"),
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

    The output shows which URLs contain movers/orderbook/broker data — share
    this output when reporting adapter issues so selectors can be calibrated.

    Examples:
        saham data stockbit spy
        saham data stockbit spy --target orderbook --ticker BBRI
        saham data stockbit spy --target stock --ticker BBCA   (named broker breakdown)
        saham data stockbit spy --target broker-scan           (foreign top stocks)
        saham data stockbit spy --wait 10 --output journals/my-capture.json
    """
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit import spy_stockbit_session

    resolved_session = session or DEFAULT_SESSION_FILE
    resolved_output = output or DEFAULT_SPY_OUTPUT

    typer.echo(f"Target  : {target}" + (f" ({ticker})" if target in ("orderbook", "stock") else ""))
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

    if result.get("broker_candidates"):
        typer.echo(typer.style("Possible BROKER endpoints:", fg=typer.colors.GREEN))
        for url in result["broker_candidates"]:
            typer.echo(f"  ★ {url}")
    elif target in ("stock", "broker-scan"):
        typer.echo(typer.style("No broker endpoint detected.", fg=typer.colors.YELLOW))
        typer.echo("  Re-run with --wait 15; or check the full URL list below.")

    typer.echo("")
    typer.echo("All unique JSON URLs captured:")
    for url in result["unique_json_urls"]:
        typer.echo(f"  {url}")

    typer.echo("")
    typer.echo(f"Full capture saved → {result['output_file']}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  1. Share the URLs above (or the JSON file) to calibrate the adapter")
    typer.echo("  2. Once endpoints are confirmed: saham data stockbit test")


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
        saham data stockbit test
        saham data stockbit test --no-headless    (see the browser)
        saham data stockbit test --ticker BMRI
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
            typer.echo(f"  {'TICKER':<8} {'IEV':>12} {'IEP':>10}")
            typer.echo("  " + "-" * 33)
            for m in movers[:10]:
                iep_str = f"{m.iep:,}" if m.iep is not None else "—"
                typer.echo(f"  {m.ticker:<8} {m.iev:>12,} {iep_str:>10}")
            if len(movers) > 10:
                typer.echo(f"  ... and {len(movers) - 10} more")
        else:
            typer.echo(typer.style("  ✗ 0 movers returned", fg=typer.colors.RED))
            typer.echo("")
            typer.echo("  Diagnosis:")
            typer.echo("    — API intercept: no URL matched movers patterns")
            typer.echo("    — DOM scrape:    no table rows found")
            typer.echo("    — Next step:     saham data stockbit spy --target screener")
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
            typer.echo(f"  Next step: saham data stockbit spy --target orderbook --ticker {ticker}")
    except Exception as e:
        typer.echo(typer.style(f"  ✗ Error: {e}", fg=typer.colors.RED))

    typer.echo("")


@stockbit_app.command("browse")
def browse(
    url: Annotated[
        Optional[str],
        typer.Option("--url", "-u", help="Stockbit page to open"),
    ] = None,
    session: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to session file"),
    ] = None,
) -> None:
    """
    Open a headed browser with the saved session and keep it open for browsing.

    Uses the persistent profile (.stockbit_profile/) if available. The browser
    stays open until you press Ctrl+C.

    Examples:
        saham data stockbit browse
        saham data stockbit browse --url https://stockbit.com/stocks/BBCA
    """
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit import browse_stockbit_session

    resolved = session or DEFAULT_SESSION_FILE
    target = url or "https://stockbit.com/stream"
    try:
        browse_stockbit_session(session_file=resolved, url=target)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@stockbit_app.command("fetch-top5")
def fetch_top5(
    top: Annotated[
        int,
        typer.Option("--top", help="How many top IEV movers to fetch", min=1, max=20),
    ] = 5,
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
    Fetch top-N IEV movers and their live orderbook snapshots in one session.

    Calls the Exodus IEV movers API (all boards: main + special monitoring),
    takes the top N by IEV, then fetches the orderbook for each ticker.
    Displays a ranked table with best bid and best offer.

    Examples:
        saham data stockbit fetch-top5
        saham data stockbit fetch-top5 --top 10
        saham data stockbit fetch-top5 --no-headless   (see the browser)
    """
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider

    resolved_session = session or DEFAULT_SESSION_FILE
    provider = PlaywrightStockbitProvider(
        session_file=resolved_session,
        headless=headless,
    )

    typer.echo("")
    typer.echo(f"Fetching top {top} IEV movers + orderbooks...")
    typer.echo("(one browser session — this may take 10-20 seconds)")
    typer.echo("")

    try:
        results = provider.fetch_top5_iev_with_orderbooks(top_n=top)
    except Exception as e:
        typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
        raise typer.Exit(1)

    if not results:
        typer.echo(typer.style("No results returned.", fg=typer.colors.YELLOW))
        typer.echo("Try: saham data stockbit login  (session may have expired)")
        return

    typer.echo(
        f"  {'#':<4} {'TICKER':<8} {'IEV':>12} {'IEP':>10}   "
        f"{'BEST BID':>10} {'LOTS':>8}   {'BEST OFFER':>10} {'LOTS':>8}"
    )
    typer.echo("  " + "-" * 79)

    for rank, r in enumerate(results, start=1):
        iep_str = f"{r.iep:,}" if r.iep is not None else "—"
        bid_str = f"{r.best_bid:,.0f}" if r.best_bid is not None else "—"
        bid_lots_str = f"{r.best_bid_lots:,}" if r.best_bid_lots is not None else "—"
        offer_str = f"{r.best_offer:,.0f}" if r.best_offer is not None else "—"
        offer_lots_str = f"{r.best_offer_lots:,}" if r.best_offer_lots is not None else "—"

        line = (
            f"  {rank:<4} {r.ticker:<8} {r.iev:>12,} {iep_str:>10}   "
            f"{bid_str:>10} {bid_lots_str:>8}   {offer_str:>10} {offer_lots_str:>8}"
        )
        typer.echo(typer.style(line, fg=typer.colors.GREEN) if rank <= 3 else line)

    typer.echo("")
