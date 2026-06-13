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
from src.application.use_case.fetch_market_data import (
    FetchMarketDataRequest,
    FetchMarketDataUseCase,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProviderError,
)
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider
from src.infrastructure.data_providers.stockbit import StockbitBrokerDataProvider
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

DEFAULT_DB_PATH = Path("data.db")
DEFAULT_DAYS = 90
STOCKBIT_TOKEN_PATH = Path("stockbit_token.json")


def _cached_status(latest: date, end_date: date) -> str:
    """Return an explicit cache status for update output."""
    lag_days = (end_date - latest).days
    if lag_days <= 0:
        return "cached-current"
    return f"cached({lag_days}d lag)"


def _no_new_data_status(latest: date | None) -> str:
    if latest is None:
        return "provider-no-data"
    return f"provider-no-new-data(latest={latest.isoformat()})"


def _is_cached_status(status: str) -> bool:
    return status == "cached-current"


def _auto_broker_provider():
    """Return Stockbit if token exists, IDX otherwise."""
    if STOCKBIT_TOKEN_PATH.exists():
        provider = StockbitBrokerDataProvider()
        if provider.is_authenticated():
            return provider, "stockbit"
    return IdxBrokerDataProvider(), "idx"


def _fetch_candles(
    ticker: str,
    days: int,
    db_path: Path,
    provider_name: str,
    refresh: bool,
) -> str:
    """Fetch candles for one ticker. Returns status string."""
    from src.infrastructure.data_providers.idx_market import IdxMarketDataProvider

    if provider_name == "idx":
        provider = IdxMarketDataProvider()
    else:
        provider = YahooFinanceProvider()

    repo = SQLiteMarketRepository(db_path=db_path)

    end_date = date.today()
    days_to_fetch = days
    force_provider = refresh
    previous_latest: date | None = None

    if not refresh:
        existing = repo.get_date_range(ticker)
        if existing:
            _, latest = existing
            previous_latest = latest
            if latest >= end_date:
                return _cached_status(latest, end_date)
            # Only fetch the gap from latest+1 to today
            days_to_fetch = (end_date - (latest + timedelta(days=1))).days + 1
            force_provider = True

    use_case = FetchMarketDataUseCase(provider=provider, repository=repo)

    try:
        resp = use_case.execute(
            FetchMarketDataRequest(
                ticker=ticker,
                days=days_to_fetch,
                refresh=force_provider,
            )
        )
        if previous_latest is not None:
            updated_range = repo.get_date_range(ticker)
            updated_latest = updated_range[1] if updated_range else previous_latest
            if updated_latest <= previous_latest:
                return _no_new_data_status(previous_latest)
            new_candles = repo.get_candles(
                ticker,
                start_date=previous_latest + timedelta(days=1),
                end_date=updated_latest,
            )
            return f"+{len(new_candles)}d"
        return f"+{resp.count}d"
    except Exception as e:
        return f"ERR:{str(e)[:30]}"


def _fetch_broker(
    ticker: str,
    days: int,
    db_path: Path,
    broker_provider,
    refresh: bool,
) -> str:
    """Fetch broker flow for one ticker. Returns status string."""
    if ticker.startswith("^"):
        return "n/a:index"

    end_date = date.today()
    repo = SQLiteBrokerRepository(db_path)
    previous_latest: date | None = None

    if not refresh:
        existing = repo.get_date_range(ticker)
        if existing:
            _, latest = existing
            previous_latest = latest
            if latest >= end_date:
                return _cached_status(latest, end_date)
            # Only fetch the gap from latest+1 to today
            start_date = latest + timedelta(days=1)
        else:
            start_date = end_date - timedelta(days=days)
    else:
        start_date = end_date - timedelta(days=days)

    use_case = FetchBrokerDataUseCase(broker_provider, repo)

    try:
        resp = use_case.execute(
            FetchBrokerDataRequest(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                refresh=refresh,
            )
        )
        if previous_latest is not None and not resp.summaries:
            return _no_new_data_status(previous_latest)
        return f"+{len(resp.summaries)}d"
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
    broker_provider, broker_provider_name = _auto_broker_provider()

    # Header
    typer.echo(f"\nUpdating {len(ticker_list)} tickers | {days}d history")
    if not broker_only:
        typer.echo(f"  Candles: {candles_provider}")
    if not candles_only:
        typer.echo(f"  Broker:  {broker_provider_name}")
    typer.echo("")

    ok_count = 0
    fail_count = 0
    failures: list[str] = []

    for i, ticker in enumerate(ticker_list, 1):
        progress = f"[{i:>3}/{len(ticker_list)}]"
        candles_status = "skip"
        broker_status = "skip"

        if not broker_only:
            candles_status = _fetch_candles(
                ticker, days, resolved_db, candles_provider, refresh
            )

        if not candles_only:
            broker_status = _fetch_broker(
                ticker, days, resolved_db, broker_provider, refresh
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
