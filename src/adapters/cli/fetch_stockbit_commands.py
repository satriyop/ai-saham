"""
CLI commands for Stockbit browser session management and adapter diagnostics.

Commands:
  saham fetch stockbit login   — create persistent browser session profile
  saham fetch stockbit status  — check session health without opening a browser
  saham fetch stockbit spy     — capture all API traffic to identify real endpoints
  saham fetch stockbit test    — smoke-test the live adapter with saved session

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

stockbit_app = typer.Typer(
    name="stockbit",
    help="Stockbit session management and adapter diagnostics",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

DEFAULT_SPY_OUTPUT = Path("journals/stockbit-spy.json")


def _require_playwright_cli() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError:
        typer.echo(
            "playwright not installed.\nRun: pip install playwright && playwright install chromium",
            err=True,
        )
        raise typer.Exit(1)


@stockbit_app.command("login")
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
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit_provider import save_stockbit_session

    try:
        save_stockbit_session(timeout=timeout)
    except Exception as e:
        typer.echo(f"Login failed: {e}", err=True)
        raise typer.Exit(1)


@stockbit_app.command("status")
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
            "Token is not locally valid. It will refresh automatically from the\n"
            "browser profile on the next API call, or run: saham fetch stockbit login"
        )


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
) -> None:
    """
    Capture all API traffic from a Stockbit page to identify real endpoints.

    Opens a headed browser (so you can interact if needed), navigates to
    the target page, and saves every JSON API response to a file.

    The output shows which URLs contain movers/orderbook/broker data — share
    this output when reporting adapter issues so selectors can be calibrated.

    Examples:
        saham fetch stockbit spy
        saham fetch stockbit spy --target orderbook --ticker BBRI
        saham fetch stockbit spy --target stock --ticker BBCA   (named broker breakdown)
        saham fetch stockbit spy --target broker-scan           (foreign top stocks)
        saham fetch stockbit spy --wait 10 --output journals/my-capture.json
    """
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit_provider import spy_stockbit_session

    resolved_output = output or DEFAULT_SPY_OUTPUT

    typer.echo(f"Target  : {target}" + (f" ({ticker})" if target in ("orderbook", "stock") else ""))
    typer.echo(f"Wait    : {wait}s")
    typer.echo(f"Output  : {resolved_output}")
    typer.echo("")

    try:
        result = spy_stockbit_session(
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
    typer.echo("  2. Once endpoints are confirmed: saham fetch stockbit test")


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
) -> None:
    """
    Smoke-test the Stockbit adapter with the saved session.

    Runs a live fetch of movers and order book via the persisted JWT token
    and prints raw results. No browser is launched — data uses httpx directly.
    Use this to verify the adapter works after calibrating from spy output.

    Examples:
        saham fetch stockbit test
        saham fetch stockbit test --ticker BMRI
    """
    from src.infrastructure.browser.playwright_stockbit_provider import PlaywrightStockbitProvider
    from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session

    _test_session = get_stockbit_session()
    if not _test_session or not _test_session.authenticated:
        typer.echo("Stockbit session expired. Run `saham fetch stockbit login` to refresh.")
        raise typer.Exit(1)
    api_client = _test_session.api_client
    provider = PlaywrightStockbitProvider(api_client=api_client)

    # ── Test 1: movers ────────────────────────────────────────────────────
    typer.echo("")
    typer.echo("Test 1: fetch_preopen_movers(iev_min=1)")
    typer.echo("-" * 45)

    try:
        movers = provider.fetch_preopen_movers(iev_min=iev_min)
        if movers:
            typer.echo(typer.style(f"  ✓ {len(movers)} movers returned", fg=typer.colors.GREEN))
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
            typer.echo("    — Exodus API returned empty or unexpected response")
            typer.echo("    — Token may be expired: saham fetch stockbit login")
            typer.echo("    — Next step: saham fetch stockbit spy --target screener")
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
            typer.echo(
                f"  Next step: saham fetch stockbit spy --target orderbook --ticker {ticker}"
            )
    except Exception as e:
        typer.echo(typer.style(f"  ✗ Error: {e}", fg=typer.colors.RED))

    typer.echo("")


@stockbit_app.command("browse")
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
    _require_playwright_cli()
    from src.infrastructure.browser.playwright_stockbit_provider import browse_stockbit_session

    target = url or "https://stockbit.com/stream"
    try:
        browse_stockbit_session(url=target)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@stockbit_app.command("fetch-top5")
def fetch_top5(
    top: Annotated[
        int,
        typer.Option("--top", help="How many top IEV movers to fetch", min=1, max=20),
    ] = 5,
) -> None:
    """
    Fetch top-N IEV movers and their live orderbook snapshots in one session.

    Calls the Exodus IEV movers API (all boards: main + special monitoring),
    takes the top N by IEV, then fetches the orderbook for each ticker.
    Displays a ranked table with best bid and best offer. No browser is launched.

    Examples:
        saham fetch stockbit fetch-top5
        saham fetch stockbit fetch-top5 --top 10
    """
    from src.infrastructure.browser.playwright_stockbit_provider import PlaywrightStockbitProvider
    from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session

    _top5_session = get_stockbit_session()
    if not _top5_session or not _top5_session.authenticated:
        typer.echo("Stockbit session expired. Run `saham fetch stockbit login` to refresh.")
        raise typer.Exit(1)
    provider = PlaywrightStockbitProvider(api_client=_top5_session.api_client)

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
        typer.echo("Try: saham fetch stockbit login  (session may have expired)")
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
