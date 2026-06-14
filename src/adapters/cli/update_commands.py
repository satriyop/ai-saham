"""
CLI command for batch data updates.

Provides `saham update` — a single daily command to fetch fresh
candles + broker flow for a stock universe or explicit ticker list.

Auto-selects broker provider: Stockbit if token is available, IDX otherwise.

Usage:
    saham update --universe lq45          # all LQ45 stocks
    saham update --universe cached        # refresh already-cached tickers
    saham update BBCA BBRI BMRI           # explicit tickers
    saham update --universe lq45 --days 30
    saham update --universe lq45 --broker-only

Layer: Adapter
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.fetch_broker_data import (
    FetchBrokerDataRequest,
    FetchBrokerDataUseCase,
)
from src.application.use_case.refresh_market_data import (
    RefreshMarketDataRequest,
    RefreshMarketDataUseCase,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProviderError,
)
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

DEFAULT_DB_PATH = Path("data.db")
DEFAULT_DAYS = 90
STOCKBIT_PROFILE_DIR = Path(".stockbit_profile")
MARKET_START_TOLERANCE_DAYS = 7
MARKET_END_TOLERANCE_DAYS = 7


def _cached_status(latest: date, end_date: date) -> str:
    """Return an explicit cache status for update output."""
    lag_days = (end_date - latest).days
    if lag_days <= 0:
        return "cached-current"
    return f"cached({lag_days}d lag)"


def _no_new_data_status(latest: date | None) -> str:
    if latest is None:
        return "no-data"
    return f"up-to-date({latest.isoformat()})"


def _is_cached_status(status: str) -> bool:
    return status == "cached-current"


def _broker_update_status(
    added_count: int,
    updated_range: tuple[date, date] | None,
    fetch_modes: set[str],
) -> str:
    """Return an explicit broker update status for update output."""
    if added_count == 0 and updated_range is None:
        return "no-data"

    span_days = (
        (updated_range[1] - updated_range[0]).days + 1
        if updated_range
        else 0
    )
    prefix = "backfill+" if "backfill" in fetch_modes else "+"
    return f"{prefix}{added_count}rows/span={span_days}d"


def _range_update_status(
    added_count: int,
    updated_range: tuple[date, date] | None,
    fetch_modes: set[str],
) -> str:
    """Return an explicit cache update status for date-ranged data."""
    if added_count == 0 and updated_range is None:
        return "no-data"

    span_days = (
        (updated_range[1] - updated_range[0]).days + 1
        if updated_range
        else 0
    )
    prefix = "backfill+" if "backfill" in fetch_modes else "+"
    return f"{prefix}{added_count}rows/span={span_days}d"


def _echo_note_group(
    title: str,
    messages: list[str],
    color: str,
    limit: int = 12,
    footer: str | None = None,
) -> None:
    """Print a compact note group without flooding large universe updates."""
    if not messages:
        return
    typer.echo("")
    typer.echo(typer.style(title, fg=color))
    for msg in messages[:limit]:
        typer.echo(typer.style(msg, fg=color))
    remaining = len(messages) - limit
    if remaining > 0:
        typer.echo(typer.style(f"  ... {remaining} more", fg=color))
    if footer:
        typer.echo(typer.style(footer, fg=color))


def _create_broker_provider(name: str | None):
    """
    Create broker provider by explicit name, or auto-detect if name is None.

    Auto-detect order:
      1. Playwright session (.stockbit_profile/) — preferred; no token file needed
      2. IDX public API — always available fallback
    """
    if name == "stockbit-session":
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        return StockbitPlaywrightBrokerProvider(), "stockbit-session"
    if name == "idx":
        return IdxBrokerDataProvider(), "idx"
    if name is not None:
        raise ValueError(
            "Unknown broker provider: "
            f"{name}. Choose from: idx, stockbit-session"
        )

    # Auto-detect
    if STOCKBIT_PROFILE_DIR.exists():
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        provider = StockbitPlaywrightBrokerProvider()
        if provider.is_authenticated():
            return provider, "stockbit-session"
    return IdxBrokerDataProvider(), "idx"


def _fetch_candles(
    ticker: str,
    days: int,
    db_path: Path,
    provider_name: str,
    refresh: bool,
    short_history: list[str] | None = None,
) -> str:
    """Fetch candles for one ticker. Returns status string."""
    from src.infrastructure.data_providers.idx_market import IdxMarketDataProvider

    if provider_name == "idx":
        provider = IdxMarketDataProvider()
    else:
        provider = YahooFinanceProvider()

    repo = SQLiteMarketRepository(db_path=db_path)
    use_case = RefreshMarketDataUseCase(provider=provider, repository=repo)

    try:
        response = use_case.execute(
            RefreshMarketDataRequest(
                ticker=ticker,
                days=days,
                refresh=refresh,
                start_tolerance_days=MARKET_START_TOLERANCE_DAYS,
                end_tolerance_days=MARKET_END_TOLERANCE_DAYS,
            )
        )
        if short_history is not None and response.short_history_note:
            short_history.append(response.short_history_note)
        return response.status
    except Exception as e:
        return f"ERR:{str(e)[:30]}"


def _fetch_broker(
    ticker: str,
    days: int,
    db_path: Path,
    broker_provider,
    refresh: bool,
    short_history: list[str] | None = None,
) -> str:
    """Fetch broker flow for one ticker. Returns status string."""
    if ticker.startswith("^"):
        return "n/a:index"

    end_date = date.today()
    requested_start = end_date - timedelta(days=days)
    repo = SQLiteBrokerRepository(db_path)
    source = broker_provider.provider_name  # 'idx' | 'stockbit' | 'stockbit-session'
    previous_latest: date | None = None
    fetch_ranges: list[tuple[date, date, str]] = []

    if not refresh:
        # Check cache only for THIS source — IDX cache must not block Stockbit fetch
        summary_range = repo.get_date_range(ticker, source=source)
        flow_range = repo.get_foreign_flow_date_range(ticker, source=source)
        existing = flow_range or summary_range
        if existing:
            earliest, latest = existing
            previous_latest = latest
            tolerated_start = requested_start + timedelta(days=MARKET_START_TOLERANCE_DAYS)
            tolerated_end = end_date - timedelta(days=MARKET_END_TOLERANCE_DAYS)
            needs_older_backfill = earliest > tolerated_start
            needs_forward_fill = latest < tolerated_end
            if short_history is not None and needs_older_backfill:
                cached_days = (latest - earliest).days
                short_history.append(
                    f"  broker  {ticker}: {cached_days}d {source} cached (from {earliest}), "
                    f"requested {days}d — backfilling older gap"
                )
            if not needs_forward_fill and not needs_older_backfill:
                return "cached-current"
            if needs_older_backfill:
                # Cache is current or partly current but shorter than requested;
                # fill only the older missing window.
                fetch_ranges.append((
                    requested_start,
                    earliest - timedelta(days=1),
                    "backfill",
                ))
            if needs_forward_fill:
                # Only fetch the forward gap from latest+1 to today
                fetch_ranges.append((latest + timedelta(days=1), end_date, "forward"))
        else:
            fetch_ranges.append((requested_start, end_date, "initial"))
    else:
        fetch_ranges.append((requested_start, end_date, "refresh"))

    use_case = FetchBrokerDataUseCase(broker_provider, repo)
    before_flow_dates = {
        p.date for p in repo.get_foreign_flow_points(ticker, source=source)
    }
    before_summary_dates = {
        s.date for s in repo.get_broker_summaries(ticker, source=source)
    }

    try:
        fetch_modes: set[str] = set()
        for start_date, fetch_end_date, fetch_mode in fetch_ranges:
            if start_date > fetch_end_date:
                continue
            fetch_modes.add(fetch_mode)
            use_case.execute(
                FetchBrokerDataRequest(
                    ticker=ticker,
                    start_date=start_date,
                    end_date=fetch_end_date,
                    refresh=refresh,
                )
            )

        # Also fetch exact historical foreign flow (Stockbit) so the daily
        # foreign-flow series has real avg_price. Failures are soft.
        try:
            points = broker_provider.fetch_foreign_flow_history(ticker, days=days)
            if points:
                repo.save_foreign_flow_points(points)
        except Exception as e:
            if short_history is not None:
                short_history.append(f"  {ticker}: foreign-flow history unavailable ({str(e)[:60]})")

        after_flow_dates = {
            p.date for p in repo.get_foreign_flow_points(ticker, source=source)
        }
        after_summary_dates = {
            s.date for s in repo.get_broker_summaries(ticker, source=source)
        }
        added_flow_count = len(after_flow_dates - before_flow_dates)
        added_summary_count = len(after_summary_dates - before_summary_dates)
        added_count = max(added_summary_count, added_flow_count)

        if previous_latest is not None and added_count == 0:
            return _no_new_data_status(previous_latest)

        # Show new days added / total days for this source. Prefer daily flow
        # coverage because Stockbit-session summaries may be period aggregates.
        updated_range = (
            repo.get_foreign_flow_date_range(ticker, source=source)
            or repo.get_date_range(ticker, source=source)
        )
        return _broker_update_status(added_count, updated_range, fetch_modes)
    except BrokerDataAuthError:
        return "ERR:auth"
    except BrokerDataProviderError as e:
        return f"ERR:{str(e)[:30]}"
    except Exception as e:
        return f"ERR:{str(e)[:30]}"


def update(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI BMRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe", "-u",
            help="Named universe: lq45, idx80, idxcomp100, cached",
        ),
    ] = None,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Days of history to fetch", min=1),
    ] = DEFAULT_DAYS,
    candles_only: Annotated[
        bool,
        typer.Option("--candles-only", help="Skip broker flow fetch"),
    ] = False,
    broker_only: Annotated[
        bool,
        typer.Option("--broker-only", help="Skip candles fetch"),
    ] = False,
    candles_provider: Annotated[
        str,
        typer.Option("--provider", help="Candles provider: yahoo or idx"),
    ] = "yahoo",
    broker_provider: Annotated[
        Optional[str],
        typer.Option(
            "--broker-provider",
            help="Broker provider: idx or stockbit-session. Auto-detects if omitted.",
        ),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", "-r", help="Force refresh even if cached"),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Fetch fresh candles + broker flow data for a stock universe.

    Run this command once per day before screening to ensure fresh data.
    Auto-selects Stockbit broker provider if token is configured,
    otherwise falls back to IDX public API.

    Examples:
        saham update --universe lq45
        saham update --universe lq45 --days 30
        saham update BBCA BBRI BMRI
        saham update --universe cached --refresh
        saham update --universe lq45 --broker-only
        saham update BBCA --broker-provider stockbit-session --days 30
    """
    resolved_db = db_path or DEFAULT_DB_PATH

    # Resolve ticker list
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to update. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    # Determine broker provider
    try:
        broker_provider, broker_provider_name = _create_broker_provider(broker_provider)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # Header
    typer.echo(f"\nUpdating {len(ticker_list)} tickers | {days}d history")
    if not broker_only:
        typer.echo(f"  Candles: {candles_provider}")
    if not candles_only:
        typer.echo(f"  Broker:  {broker_provider_name}")
    typer.echo("  Status: +Nrows = new rows stored; span = calendar cache coverage")
    typer.echo("")

    ok_count = 0
    fail_count = 0
    failures: list[str] = []
    candle_short_history: list[str] = []
    broker_backfills: list[str] = []

    for i, ticker in enumerate(ticker_list, 1):
        progress = f"[{i:>3}/{len(ticker_list)}]"
        candles_status = "skip"
        broker_status = "skip"

        if not broker_only:
            candles_status = _fetch_candles(
                ticker, days, resolved_db, candles_provider, refresh, candle_short_history
            )

        if not candles_only:
            broker_status = _fetch_broker(
                ticker, days, resolved_db, broker_provider, refresh, broker_backfills
            )

        any_error = "ERR:" in candles_status or "ERR:" in broker_status
        all_cached = _is_cached_status(candles_status) and _is_cached_status(broker_status)

        if any_error:
            fail_count += 1
            failures.append(ticker)
            status_color = typer.colors.RED
        else:
            ok_count += 1
            status_color = typer.colors.BRIGHT_BLACK if all_cached else typer.colors.GREEN

        typer.echo(
            f"  {progress} {ticker:<6} "
            + typer.style(
                f"candles={candles_status} broker={broker_status}",
                fg=status_color,
            )
        )

    # Summary
    typer.echo("")
    typer.echo("=" * 50)
    typer.echo(
        f"Done: {ok_count} ok"
        + (f", {fail_count} failed" if fail_count else "")
    )
    if failures:
        typer.echo(f"Failed: {', '.join(failures)}")
    _echo_note_group(
        title=(
            f"⚠  Candle cache shorter than --days {days} for "
            f"{len(candle_short_history)} ticker(s); older candle gaps were fetched automatically:"
        ),
        messages=candle_short_history,
        color=typer.colors.YELLOW,
        footer="   Use --refresh only when you want to re-fetch the full requested candle window.",
    )
    _echo_note_group(
        title=(
            f"Broker history shorter than --days {days} for "
            f"{len(broker_backfills)} ticker(s); older broker gaps were fetched automatically:"
        )
        if broker_backfills
        else "",
        messages=broker_backfills,
        color=typer.colors.CYAN,
    )
