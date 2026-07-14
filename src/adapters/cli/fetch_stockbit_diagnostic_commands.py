"""
CLI commands for Stockbit adapter diagnostics.

Commands:
  saham fetch stockbit test        — smoke-test the live adapter with saved session
  saham fetch stockbit fetch-top5  — fetch top-N IEV movers with orderbook snapshots

Layer: Adapter
"""

from __future__ import annotations

from typing import Annotated

import typer

from src.adapters.cli.fetch_stockbit_diagnostic_factory import (
    create_authenticated_stockbit_provider,
)


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
    try:
        provider = create_authenticated_stockbit_provider()
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

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
    try:
        provider = create_authenticated_stockbit_provider()
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

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
