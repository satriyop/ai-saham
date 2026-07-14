"""
CLI command for capturing Stockbit API traffic to identify real endpoints.

Commands:
  saham fetch stockbit spy — capture all API traffic to identify real endpoints

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.fetch_stockbit_session_commands import _require_playwright_cli

DEFAULT_SPY_OUTPUT = Path("journals/stockbit-spy.json")


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
