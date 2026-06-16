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
from src.application.use_case.fetch_broker_daily_flows import (
    FetchBrokerDailyFlowsRequest,
    FetchBrokerDailyFlowsResponse,
    FetchBrokerDailyFlowsUseCase,
)
from src.application.use_case.refresh_market_data import (
    RefreshMarketDataRequest,
    RefreshMarketDataUseCase,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProviderError,
)
from src.application.use_case.fetch_stock_meta import (
    FetchStockMetaRequest,
    FetchStockMetaUseCase,
)
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.data_providers.yahoo_stock_meta import YahooStockMetaProvider
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)
from src.infrastructure.persistence.sqlite_stock_meta_repository import (
    SQLiteStockMetaRepository,
)

DEFAULT_DB_PATH = Path("data.db")
DEFAULT_DAYS = 90
STOCKBIT_PROFILE_DIR = Path(".stockbit_profile")

# Benchmark ticker always included in every update run.
# Required by: saham analyze regime, saham trade swing analyze (market context).
_BENCHMARK_TICKER = "^JKSE"
MARKET_START_TOLERANCE_DAYS = 7
MARKET_END_TOLERANCE_DAYS = 7


def _fmt_status(s: str) -> str:
    """Map internal status strings to concise display labels."""
    if s in ("cached-current", "n/a:index", "skip"):
        return s.replace("cached-current", "✓")
    if s.startswith("up-to-date("):
        return "✓"   # provider confirmed no new data — cache is current
    return s


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


def _broker_status_with_daily(
    daily_resp: "FetchBrokerDailyFlowsResponse | None",
    agg_added_count: int,
    agg_updated_range: "tuple[date, date] | None",
    fetch_modes: set[str],
) -> str:
    """Combine daily-flow and aggregate-flow results into a single status string.

    Examples:
      daily:+636rows/12codes/365d flow:+1rows/366d  (both ran)
      daily:+636rows/12codes/365d                   (only daily ran)
      +1rows/span=366d                              (IDX — no daily flow)
    """
    # Daily-flow part (only when the provider actually fetched from the API)
    daily_part: str | None = None
    if daily_resp is not None and daily_resp.fetched_count > 0:
        span = (
            (daily_resp.cached_range[1] - daily_resp.cached_range[0]).days + 1
            if daily_resp.cached_range
            else 0
        )
        daily_part = (
            f"daily:+{daily_resp.fetched_count}rows"
            f"/{daily_resp.active_codes}codes/{span}d"
        )

    # Aggregate-flow part
    agg_part: str | None = None
    if agg_added_count > 0 or agg_updated_range:
        span = (
            (agg_updated_range[1] - agg_updated_range[0]).days + 1
            if agg_updated_range
            else 0
        )
        prefix = "backfill+" if "backfill" in fetch_modes else "+"
        agg_part = f"flow:{prefix}{agg_added_count}rows/{span}d"

    if daily_part and agg_part:
        return f"{daily_part} {agg_part}"
    if daily_part:
        return daily_part
    if agg_part:
        return _broker_update_status(agg_added_count, agg_updated_range, fetch_modes)
    return "no-data"


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

    The returned provider is used ONLY for broker_daily_flow and foreign_flow_points.
    broker_summaries always go through IdxBrokerDataProvider (accurate total_value).

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


from dataclasses import dataclass as _dataclass


@_dataclass(frozen=True)
class BrokerFetchResult:
    """
    Split status for the two broker data streams written by _fetch_broker.

    summaries — broker_summaries table (always via IDX public API)
    flow      — foreign_flow_points + broker_daily_flow (via Stockbit or IDX)

    Status values:
      "cached-current"     data is up-to-date, no rows needed
      "up-to-date(DATE)"   provider confirmed nothing new since DATE
      "+Nrows/span=Nd"     new rows stored
      "daily:+Nrows/..."   broker_daily_flow rows stored
      "n/a:index"          not applicable (index ticker)
      "ERR:..."            fetch failed
    """
    summaries: str
    flow: str


def _flow_status(
    daily_resp: "FetchBrokerDailyFlowsResponse | None",
    added_flow_count: int,
    flow_range: "tuple[date, date] | None",
    fetch_modes: set[str],
) -> str:
    """Build the display status for foreign_flow_points + broker_daily_flow."""
    daily_part: str | None = None
    if daily_resp is not None and daily_resp.fetched_count > 0:
        span = (
            (daily_resp.cached_range[1] - daily_resp.cached_range[0]).days + 1
            if daily_resp.cached_range else 0
        )
        daily_part = f"daily:+{daily_resp.fetched_count}rows/{daily_resp.active_codes}codes/{span}d"

    flow_part: str | None = None
    if added_flow_count > 0 and flow_range:
        span = (flow_range[1] - flow_range[0]).days + 1
        prefix = "backfill+" if "backfill" in fetch_modes else "+"
        flow_part = f"flow:{prefix}{added_flow_count}rows/{span}d"

    if daily_part and flow_part:
        return f"{daily_part} {flow_part}"
    if daily_part:
        return daily_part
    if flow_part:
        return flow_part
    return "cached-current"


def _fetch_broker(
    ticker: str,
    days: int,
    db_path: Path,
    broker_provider,
    refresh: bool,
    short_history: list[str] | None = None,
    _idx_summary_provider=None,  # injectable for testing; production code uses IdxBrokerDataProvider
) -> BrokerFetchResult:
    """Fetch broker flow for one ticker. Returns split status for summaries and flow tables."""
    if ticker.startswith("^"):
        return BrokerFetchResult(summaries="n/a:index", flow="n/a:index")

    end_date = date.today()
    requested_start = end_date - timedelta(days=days)
    repo = SQLiteBrokerRepository(db_path)
    source = broker_provider.provider_name  # 'idx' | 'stockbit' | 'stockbit-session'
    previous_latest: date | None = None
    fetch_ranges: list[tuple[date, date, str]] = []

    # Per-broker daily flow — runs before the aggregate cache check so it is
    # never skipped by an early "cached-current" return below.
    daily_resp: FetchBrokerDailyFlowsResponse | None = None
    if hasattr(broker_provider, "fetch_broker_daily_flows"):
        try:
            daily_uc = FetchBrokerDailyFlowsUseCase(broker_provider, repo)
            daily_resp = daily_uc.execute(FetchBrokerDailyFlowsRequest(
                ticker=ticker,
                days=days,
                refresh=refresh,
            ))
        except Exception as e:
            if short_history is not None:
                short_history.append(
                    f"  {ticker}: broker daily flow unavailable ({str(e)[:60]})"
                )

    if not refresh:
        # broker_summaries always come from IDX; only foreign_flow_points use the Stockbit source
        summary_range = repo.get_date_range(ticker, source='idx')
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
                # Aggregate is current; daily flow may still have fetched new named-broker rows.
                if daily_resp is not None and daily_resp.fetched_count > 0:
                    span = (
                        (daily_resp.cached_range[1] - daily_resp.cached_range[0]).days + 1
                        if daily_resp.cached_range
                        else 0
                    )
                    return BrokerFetchResult(
                        summaries="cached-current",
                        flow=f"daily:+{daily_resp.fetched_count}rows/{daily_resp.active_codes}codes/{span}d",
                    )
                return BrokerFetchResult(summaries="cached-current", flow="cached-current")
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

    # broker_summaries always use IDX (accurate total_value); Stockbit is for daily_flow + flow_points.
    # If broker_provider is already IDX, reuse it. Otherwise create an IDX provider for summaries.
    if _idx_summary_provider is not None:
        idx_summary_provider = _idx_summary_provider
    elif broker_provider.provider_name == "idx":
        idx_summary_provider = broker_provider
    else:
        idx_summary_provider = IdxBrokerDataProvider()
    use_case = FetchBrokerDataUseCase(idx_summary_provider, repo)
    before_flow_dates = {
        p.date for p in repo.get_foreign_flow_points(ticker, source=source)
    }
    before_summary_dates = {
        s.date for s in repo.get_broker_summaries(ticker, source='idx')
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

        # Fetch aggregate foreign flow history for VWAP/trend context.
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
            s.date for s in repo.get_broker_summaries(ticker, source='idx')
        }
        added_flow_count = len(after_flow_dates - before_flow_dates)
        added_summary_count = len(after_summary_dates - before_summary_dates)
        added_count = max(added_summary_count, added_flow_count)

        if previous_latest is not None and added_count == 0:
            # Aggregate had nothing new — but daily flow may still have fetched named-broker rows.
            no_new = _no_new_data_status(previous_latest)
            if daily_resp is not None and daily_resp.fetched_count > 0:
                span = (
                    (daily_resp.cached_range[1] - daily_resp.cached_range[0]).days + 1
                    if daily_resp.cached_range
                    else 0
                )
                return BrokerFetchResult(
                    summaries=no_new,
                    flow=f"daily:+{daily_resp.fetched_count}rows/{daily_resp.active_codes}codes/{span}d",
                )
            return BrokerFetchResult(summaries=no_new, flow=no_new)

        # New rows were stored — report summaries and flow separately.
        updated_summ_range = repo.get_date_range(ticker, source='idx')
        updated_flow_range = repo.get_foreign_flow_date_range(ticker, source=source)

        summ_status = _broker_update_status(added_summary_count, updated_summ_range, fetch_modes)
        flow_status = _flow_status(daily_resp, added_flow_count, updated_flow_range, fetch_modes)

        return BrokerFetchResult(summaries=summ_status, flow=flow_status)
    except BrokerDataAuthError:
        return BrokerFetchResult(summaries="ERR:auth", flow="ERR:auth")
    except BrokerDataProviderError as e:
        err = f"ERR:{str(e)[:30]}"
        return BrokerFetchResult(summaries=err, flow=err)
    except Exception as e:
        err = f"ERR:{str(e)[:30]}"
        return BrokerFetchResult(summaries=err, flow=err)


def _print_table_summary(
    db_path: Path,
    stock_tickers: list[str],
    candles_provider: str,
    broker_provider_name: str,
    no_meta: bool,
    candles_only: bool,
    broker_only: bool,
) -> None:
    """Print a concise summary of each table written during this run."""
    import sqlite3 as _sqlite3

    # Tables, their source, and a plain-English description of what they store.
    # Each entry: (table, source_label, description, query_fn)
    # query_fn receives a cursor and the IN-clause placeholder string.
    stock_ph = ",".join("?" * len(stock_tickers))

    def _count(cur, sql, params=()):
        row = cur.execute(sql, params).fetchone()
        return row[0] if row else 0

    try:
        conn = _sqlite3.connect(db_path)
        cur = conn.cursor()

        rows_candles = _count(
            cur,
            f"SELECT COUNT(*) FROM candles WHERE ticker IN ({stock_ph})",
            stock_tickers,
        ) if not broker_only else None

        rows_summaries = _count(
            cur,
            f"SELECT COUNT(*) FROM broker_summaries WHERE ticker IN ({stock_ph}) AND source='idx'",
            stock_tickers,
        ) if not candles_only else None

        rows_flow_points = _count(
            cur,
            f"SELECT COUNT(*) FROM foreign_flow_points WHERE ticker IN ({stock_ph})",
            stock_tickers,
        ) if not candles_only else None

        rows_daily_flow = _count(
            cur,
            f"SELECT COUNT(*) FROM broker_daily_flow WHERE ticker IN ({stock_ph})",
            stock_tickers,
        ) if not candles_only else None

        rows_meta = _count(
            cur,
            f"SELECT COUNT(*) FROM stock_meta WHERE ticker IN ({stock_ph})",
            stock_tickers,
        ) if not no_meta else None

        conn.close()
    except Exception:
        return  # summary is informational; never crash the run for it

    W = 74
    typer.echo(f"\n{'─' * W}")
    typer.echo(f"  {'TABLE':<22} {'SOURCE':<18} {'ROWS':>7}   CONTAINS")
    typer.echo(f"{'─' * W}")

    def _row(table, source, rows, description):
        if rows is None:
            return
        typer.echo(f"  {table:<22} {source:<18} {rows:>7,}   {description}")

    _row(
        "candles",
        candles_provider,
        rows_candles,
        "Daily OHLCV price history per ticker",
    )
    _row(
        "broker_summaries",
        "idx",
        rows_summaries,
        "Foreign buy/sell totals + top named brokers per day",
    )
    _row(
        "foreign_flow_points",
        broker_provider_name,
        rows_flow_points,
        "Net foreign flow timeseries (IDR value + lots) per ticker",
    )
    _row(
        "broker_daily_flow",
        broker_provider_name,
        rows_daily_flow,
        "Per-broker named buy/sell amounts per ticker per day",
    )
    _row(
        "stock_meta",
        "yahoo",
        rows_meta,
        "Sector/industry classification (GICS, TTL-cached)",
    )
    typer.echo(f"{'─' * W}")
    typer.echo(f"  Row counts are totals for the {len(stock_tickers)} stock ticker(s) in this run (all dates).")


def _fetch_meta(ticker: str, db_path: Path) -> str:
    """Fetch sector/industry metadata for one ticker. Returns a status string."""
    if ticker.startswith("^"):
        return "n/a:index"

    try:
        repo = SQLiteStockMetaRepository(db_path)
        provider = YahooStockMetaProvider()
        use_case = FetchStockMetaUseCase(provider=provider, repository=repo)
        result = use_case.execute(FetchStockMetaRequest(ticker=ticker))

        if result.status == "cached":
            return f"cached({result.cached_days}d)"
        if result.status == "new":
            return f"new({result.sector or '?'})"
        if result.status == "changed":
            return f"changed→{result.sector or '?'}"
        if result.status == "verified":
            return "verified"
        # error
        return f"ERR:{(result.error or 'unknown')[:30]}"
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
    no_meta: Annotated[
        bool,
        typer.Option("--no-meta", help="Skip sector/industry metadata fetch"),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Fetch fresh candles + broker flow + sector metadata for a stock universe.

    Always includes ^JKSE (benchmark) for regime analysis.
    Sector/industry data is fetched via Yahoo Finance and cached for 30 days
    (only re-fetched when stale). Use --no-meta to skip.

    Examples:
        saham data update --universe lq45
        saham data update --universe lq45 --days 30
        saham data update BBCA BBRI BMRI
        saham data update --universe cached --refresh
        saham data update --universe lq45 --broker-only
        saham data update BBCA --broker-provider stockbit-session --days 30
        saham data update --universe lq45 --no-meta
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

    # Always include benchmark — required for regime and swing analysis.
    if _BENCHMARK_TICKER not in ticker_list:
        ticker_list = ticker_list + [_BENCHMARK_TICKER]

    # Determine broker provider
    try:
        broker_provider, broker_provider_name = _create_broker_provider(broker_provider)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # Header
    typer.echo(f"\nUpdating {len(ticker_list)} tickers | {days}d history")
    if not broker_only:
        typer.echo(f"  Candles:          {candles_provider}")
    if not candles_only:
        # broker_summaries always route to IDX regardless of the selected provider;
        # flow tables (foreign_flow_points, broker_daily_flow) use the chosen provider.
        typer.echo(f"  Broker summaries: idx  (foreign totals + named brokers)")
        typer.echo(f"  Broker flow:      {broker_provider_name}  (net flow timeseries + daily named breakdown)")
    if not no_meta:
        typer.echo("  Meta:             yahoo  (sector/industry, 30d TTL)")
    typer.echo("  Legend:  ✓ = up-to-date  +N = new rows stored  ERR: = failed  skip = not requested")
    typer.echo("")

    ok_count = 0
    fail_count = 0
    failures: list[str] = []
    candle_short_history: list[str] = []
    broker_backfills: list[str] = []
    meta_changed: list[str] = []

    for i, ticker in enumerate(ticker_list, 1):
        progress = f"[{i:>3}/{len(ticker_list)}]"
        candles_status = "skip"
        broker_result = BrokerFetchResult(summaries="skip", flow="skip")
        meta_status = "skip"

        if not broker_only:
            candles_status = _fetch_candles(
                ticker, days, resolved_db, candles_provider, refresh, candle_short_history
            )

        if not candles_only:
            broker_result = _fetch_broker(
                ticker, days, resolved_db, broker_provider, refresh, broker_backfills
            )

        if not no_meta:
            meta_status = _fetch_meta(ticker, resolved_db)
            if meta_status.startswith("changed"):
                meta_changed.append(f"  {ticker}: {meta_status}")

        any_error = (
            "ERR:" in candles_status
            or "ERR:" in broker_result.summaries
            or "ERR:" in broker_result.flow
        )
        all_cached = (
            _is_cached_status(candles_status)
            and _is_cached_status(broker_result.summaries)
            and _is_cached_status(broker_result.flow)
            and (no_meta or meta_status.startswith("cached"))
        )

        if any_error:
            fail_count += 1
            failures.append(ticker)
            status_color = typer.colors.RED
        else:
            ok_count += 1
            status_color = typer.colors.BRIGHT_BLACK if all_cached else typer.colors.GREEN

        status_line = (
            f"candles={_fmt_status(candles_status)}"
            f"  summ={_fmt_status(broker_result.summaries)}"
            f"  flow={_fmt_status(broker_result.flow)}"
        )
        if not no_meta:
            status_line += f"  meta={meta_status}"

        typer.echo(
            f"  {progress} {ticker:<6} "
            + typer.style(status_line, fg=status_color)
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
    _echo_note_group(
        title=f"Sector classification changed for {len(meta_changed)} ticker(s):" if meta_changed else "",
        messages=meta_changed,
        color=typer.colors.YELLOW,
    )

    # Table summary — exclude index tickers (^JKSE) since they have no broker/meta rows
    stock_tickers_only = [t for t in ticker_list if not t.startswith("^")]
    _print_table_summary(
        db_path=resolved_db,
        stock_tickers=stock_tickers_only,
        candles_provider=candles_provider,
        broker_provider_name=broker_provider_name,
        no_meta=no_meta,
        candles_only=candles_only,
        broker_only=broker_only,
    )
