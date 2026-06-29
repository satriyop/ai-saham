"""
CLI commands for active intraday trading workflows.

Layer: Adapter
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_intraday_display import (
    display_confirmations,
    display_intraday_review,
    format_opening_observation_status,
    format_ticker_preview,
)
from src.application.services.bootstrap import create_indicator_registry
from src.application.services.universe_loader import UniverseNotFoundError, resolve_tickers
from src.application.use_case.confirm_intraday_open_use_case import (
    ConfirmIntradayOpenRequest,
    ConfirmIntradayOpenUseCase,
)
from src.application.use_case.intraday_backtest_use_case import (
    IntradayBacktestRequest,
    IntradayBacktestUseCase,
)
from src.application.use_case.resolve_opening_prices_use_case import (
    OpeningPriceObservation,
    ResolveOpeningPricesRequest,
    ResolveOpeningPricesUseCase,
)
from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmation,
    IntradayConfirmationCandidate,
    IntradayConfirmationJournalEntry,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_SIDECAR_PATH = Path(APP_CFG.storage.intraday_sidecar)
DEFAULT_CONFIRMATION_PATH = Path(APP_CFG.storage.intraday_confirmation)
DEFAULT_CONFIRMATION_JOURNAL_PATH = Path(APP_CFG.storage.intraday_confirmation_journal)
DEFAULT_REGIME_UNIVERSE = APP_CFG.analysis.regime_universe
DEFAULT_REGIME_BENCHMARK = APP_CFG.analysis.benchmark


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _load_confirmation_candidates(
    session_path: Path,
    opening_prices: dict[str, Decimal],
    observations: dict[str, OpeningPriceObservation] | None = None,
) -> tuple[date, list[IntradayConfirmationCandidate], dict[str, dict]]:
    with open(session_path) as f:
        data = json.load(f)

    screened_at = date.fromisoformat(data["screened_at"])
    candidates: list[IntradayConfirmationCandidate] = []
    extras: dict[str, dict] = {}  # {ticker: {prev_high, prev_low, entry_range_low}}
    observations = observations or {}

    for row in data.get("candidates", []):
        ticker = str(row["ticker"]).upper()
        observation = observations.get(ticker)
        candidates.append(
            IntradayConfirmationCandidate(
                ticker=ticker,
                opening_price=opening_prices.get(ticker),
                iev=row.get("iev"),
                entry_range_low=_decimal_or_none(row.get("entry_range_low")),
                entry_range_high=_decimal_or_none(row.get("entry_range_high")),
                suggested_entry=_decimal_or_none(row.get("suggested_entry")),
                atr_stop=_decimal_or_none(row.get("atr_stop")),
                trend=row.get("trend"),
                rsi=_decimal_or_none(row.get("rsi")),
                gap_pct=_decimal_or_none(row.get("gap_pct")),
                opening_broker_backing_tag=row.get("opening_broker_backing_tag"),
                fvwap_discount_pct=_decimal_or_none(row.get("fvwap_discount_pct")),
                opening_price_source=observation.source if observation else None,
                opening_price_confidence=observation.confidence if observation else None,
                opening_price_timestamp=(
                    observation.timestamp.isoformat()
                    if observation and observation.timestamp
                    else None
                ),
                auto_confirmed=observation.auto_confirmed if observation else False,
                manual_override=observation.manual_override if observation else False,
            )
        )
        extras[ticker] = {
            "prev_high": row.get("prev_high"),
            "prev_low": row.get("prev_low"),
            "entry_range_low": row.get("entry_range_low"),
            "entry_range_high": row.get("entry_range_high"),
            "opening_broker_backing_tag": row.get("opening_broker_backing_tag"),
            "fvwap_discount_pct": row.get("fvwap_discount_pct"),
            "opening_price_source": observation.source if observation else None,
            "opening_price_confidence": observation.confidence if observation else None,
            "opening_price_reason": observation.reason if observation else None,
            "auto_confirmed": observation.auto_confirmed if observation else False,
            "manual_override": observation.manual_override if observation else False,
        }

    return screened_at, candidates, extras


def _load_confirmation_tickers(session_path: Path) -> tuple[date, list[str]]:
    with open(session_path) as f:
        data = json.load(f)
    screened_at = date.fromisoformat(data["screened_at"])
    tickers = [str(row["ticker"]).upper() for row in data.get("candidates", [])]
    return screened_at, tickers


def _write_confirmation_sidecar(
    confirmations: tuple[IntradayConfirmation, ...],
    confirmed_date: date,
    max_stop_pct: Decimal,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "artifact_type": "intraday_confirmation",
        "confirmed_at": str(confirmed_date),
        "max_stop_pct": str(max_stop_pct),
        "confirmations": [
            {
                "ticker": c.ticker,
                "decision": c.decision.value,
                "opening_price": str(c.opening_price) if c.opening_price else None,
                "planned_entry": str(c.planned_entry) if c.planned_entry else None,
                "stop_loss_price": str(c.stop_loss_price) if c.stop_loss_price else None,
                "stop_pct": str(c.stop_pct) if c.stop_pct is not None else None,
                "reasons": list(c.reasons),
                "iev": c.iev,
                "trend": c.trend,
                "rsi": str(c.rsi) if c.rsi is not None else None,
                "gap_pct": str(c.gap_pct) if c.gap_pct is not None else None,
                "opening_broker_backing_tag": c.opening_broker_backing_tag,
                "fvwap_discount_pct": (
                    str(c.fvwap_discount_pct)
                    if c.fvwap_discount_pct is not None
                    else None
                ),
                "opening_price_source": c.opening_price_source,
                "opening_price_confidence": c.opening_price_confidence,
                "opening_price_timestamp": c.opening_price_timestamp,
                "auto_confirmed": c.auto_confirmed,
                "manual_override": c.manual_override,
            }
            for c in confirmations
        ],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def confirm_open(
    opening_json: Annotated[
        Optional[str],
        typer.Option(
            "--opening-json",
            help='Manual opening prices JSON override, e.g. {"BBCA":9050}',
        ),
    ] = None,
    track_file: Annotated[
        Optional[Path],
        typer.Option(
            "--track-file",
            help="Path to track_*.json tracking file to resolve opening prices offline",
        ),
    ] = None,
    session: Annotated[
        Optional[Path],
        typer.Option("--session", help="Path to pre-open sidecar JSON"),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", help="Path to write confirmation sidecar JSON"),
    ] = None,
    max_stop: Annotated[
        float,
        typer.Option("--max-stop", help="Max stop distance as decimal, e.g. 0.07 for 7%"),
    ] = 0.07,
    headless: Annotated[
        bool,
        typer.Option(
            "--headless/--no-headless",
            help="Use headless browser for Stockbit auto-confirm",
        ),
    ] = True,
) -> None:
    """
    Confirm pre-open candidates after the opening auction clears.

    Reads the last `saham screen pre-open` sidecar and resolves opening prices,
    then emits deterministic ENTER / WAIT / SKIP decisions. No AI is used.
    """
    sidecar_path = session or DEFAULT_SIDECAR_PATH
    output_path = output or DEFAULT_CONFIRMATION_PATH

    if not sidecar_path.exists():
        typer.echo(
            f"No session sidecar found at '{sidecar_path}'.\n"
            "Run `saham screen pre-open` first.",
            err=True,
        )
        raise typer.Exit(1)

    manual_prices: dict[str, Decimal] = {}
    if opening_json:
        try:
            raw_opening = json.loads(opening_json)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid JSON in --opening-json: {e}", err=True)
            raise typer.Exit(1)

        if not isinstance(raw_opening, dict):
            typer.echo("Error: --opening-json must be a JSON object.", err=True)
            raise typer.Exit(1)

        try:
            manual_prices = {
                str(ticker).upper(): Decimal(str(price))
                for ticker, price in raw_opening.items()
                if price is not None
            }
        except Exception as e:
            typer.echo(f"Error: opening prices must be numeric: {e}", err=True)
            raise typer.Exit(1)

    if max_stop <= 0:
        typer.echo("Error: --max-stop must be positive.", err=True)
        raise typer.Exit(1)

    screened_at, tickers = _load_confirmation_tickers(sidecar_path)
    track_prices: dict[str, OpeningPriceObservation] = {}

    if track_file:
        if not track_file.exists():
            typer.echo(f"Error: Track file not found at '{track_file}'", err=True)
            raise typer.Exit(1)
        try:
            with open(track_file) as f:
                track_data = json.load(f)
        except Exception as e:
            typer.echo(f"Error parsing track file '{track_file}': {e}", err=True)
            raise typer.Exit(1)

        captured_at_str = track_data.get("captured_at")
        captured_at_dt = None
        if captured_at_str:
            try:
                from datetime import datetime
                captured_at_dt = datetime.fromisoformat(captured_at_str)
            except Exception:
                pass

        from src.application.use_case.opening_grade_use_case import _extract_observed_price

        track_tickers = track_data.get("tickers", {})
        for ticker in tickers:
            tdata = track_tickers.get(ticker)
            observed = _extract_observed_price(tdata)
            if observed is not None:
                price_val, source_val, confidence_val = observed
                track_prices[ticker] = OpeningPriceObservation(
                    ticker=ticker,
                    price=Decimal(str(price_val)),
                    source=source_val,
                    confidence=confidence_val,
                    timestamp=captured_at_dt,
                    reason=f"Resolved offline from track file {track_file.name}",
                    auto_confirmed=True,
                    manual_override=False,
                )

    running_trade_provider = None
    order_book_provider = None
    missing_resolved = [
        ticker for ticker in tickers
        if ticker not in manual_prices and ticker not in track_prices
    ]

    if track_file:
        auto_needed = False
    else:
        auto_needed = bool(missing_resolved)

    typer.echo(
        f"Confirming {len(tickers)} pre-open candidate(s) from {sidecar_path} "
        f"for {screened_at}."
    )
    if manual_prices:
        typer.echo(f"Manual opening prices supplied: {len(manual_prices)}")
    if track_prices:
        typer.echo(f"Track file opening prices resolved: {len(track_prices)}")

    if auto_needed:
        typer.echo(
            "Resolving missing opening prices from Stockbit: "
            f"{format_ticker_preview(missing_resolved)}"
        )
        typer.echo(
            "Tip: pass --opening-json or --track-file to "
            "skip browser-backed auto resolution."
        )
        try:
            from src.infrastructure.browser.playwright_stockbit_provider import (
                StockbitPlaywrightBrokerProvider,
            )
            from src.infrastructure.browser.stockbit_order_book import StockbitOrderBookProvider
            from src.infrastructure.browser.stockbit_running_trade import (
                StockbitRunningTradeProvider,
            )

            broker_provider = StockbitPlaywrightBrokerProvider(
                profile_dir=Path(APP_CFG.storage.stockbit_profile_dir),
                headless=headless,
            )
            if not broker_provider.is_authenticated():
                typer.echo(
                    "No authenticated Stockbit profile for auto confirm. "
                    "Run `saham fetch stockbit login` or "
                    "pass --opening-json / --track-file.",
                    err=True,
                )
                raise typer.Exit(1)
            running_trade_provider = StockbitRunningTradeProvider(broker_provider=broker_provider)
            order_book_provider = StockbitOrderBookProvider(broker_provider=broker_provider)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(
                f"Auto confirm setup failed: {e}. "
                "Pass --opening-json or --track-file to confirm manually.",
                err=True,
            )
            raise typer.Exit(1)

    resolver = ResolveOpeningPricesUseCase(
        running_trade_provider=running_trade_provider,
        order_book_provider=order_book_provider,
        on_observation=lambda index, total, observation: typer.echo(
            format_opening_observation_status(index, total, observation)
        ),
    )
    observations = resolver.execute(
        ResolveOpeningPricesRequest(
            tickers=tickers,
            run_date=screened_at,
            manual_prices=manual_prices,
            track_prices=track_prices,
        )
    )
    resolved_count = sum(1 for obs in observations.values() if obs.price is not None)
    typer.echo(f"Opening prices resolved: {resolved_count}/{len(tickers)}")
    unresolved = [obs for obs in observations.values() if obs.price is None]
    if unresolved:
        typer.echo("Unresolved opening prices:")
        for obs in unresolved:
            typer.echo(f"  - {obs.ticker}: {obs.reason or 'no usable opening price'}")
    opening_prices = {
        ticker: obs.price for ticker, obs in observations.items() if obs.price is not None
    }

    screened_at, candidates, extras = _load_confirmation_candidates(
        sidecar_path,
        opening_prices,
        observations,
    )

    po_config = load_pre_open_screen_config()

    _KNOWN_REGIMES = {"RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE",
                      "BULLISH", "SIDEWAYS", "WEAK"}  # legacy compat
    regime_val = None
    if sidecar_path.exists():
        try:
            with open(sidecar_path) as f:
                sidecar_data = json.load(f)
            regime_dict = sidecar_data.get("market_regime")
            if regime_dict and isinstance(regime_dict, dict):
                # New MCE format uses "regime" key; old format used "label"
                raw = regime_dict.get("regime") or regime_dict.get("label")
                if raw is not None and raw.upper() not in _KNOWN_REGIMES:
                    # Unrecognized regime: fail closed — treat as RISK_OFF to activate gates
                    typer.echo(
                        f"Warning: unrecognized regime '{raw}' in sidecar; "
                        "treating as RISK_OFF (fail-closed).",
                        err=True,
                    )
                    raw = "RISK_OFF"
                regime_val = raw
        except Exception:
            pass

    use_case = ConfirmIntradayOpenUseCase()
    result = use_case.execute(
        ConfirmIntradayOpenRequest(
            candidates=candidates,
            run_date=screened_at,
            max_stop_pct=Decimal(str(max_stop)),
            tick_friction_gate=po_config.tick_friction_gate,
            min_target_ticks=po_config.min_target_ticks,
            min_stop_ticks=po_config.min_stop_ticks,
            regime=regime_val,
            regime_gate_enabled=po_config.regime_gate_enabled,
            tighten_in_regimes=tuple(po_config.tighten_in_regimes),
            gap_pct_tightening_factor=Decimal(str(po_config.gap_pct_tightening_factor)),
            require_backed_in_weak=po_config.require_backed_in_weak,
        )
    )

    display_confirmations(
        result.confirmations,
        result.confirmed_date,
        result.max_stop_pct,
        extras=extras,
    )
    _write_confirmation_sidecar(
        result.confirmations,
        result.confirmed_date,
        result.max_stop_pct,
        output_path,
    )


def _confirm_log_impl(confirmation_path: Path, journal_path: Path) -> None:
    """Core intraday log logic — called by both the legacy subcommand and the unified trade log."""
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )
    from src.infrastructure.persistence.trade_journal_jsonl_writer import (
        TradeJournalJsonlWriter,
        intraday_entry_to_record,
    )

    if not confirmation_path.exists():
        typer.echo(
            f"No confirmation sidecar found at '{confirmation_path}'.\n"
            "Run `saham trade confirm` first.",
            err=True,
        )
        raise typer.Exit(1)

    with open(confirmation_path) as f:
        data = json.load(f)

    confirmed_at = date.fromisoformat(data["confirmed_at"])
    entries = [
        IntradayConfirmationJournalEntry(
            confirmed_at=confirmed_at,
            ticker=row["ticker"],
            decision=row["decision"],
            reason_codes=tuple(row.get("reasons", [])),
            opening_price=_decimal_or_none(row.get("opening_price")),
            planned_entry=_decimal_or_none(row.get("planned_entry")),
            stop_loss_price=_decimal_or_none(row.get("stop_loss_price")),
            stop_pct=_decimal_or_none(row.get("stop_pct")),
            iev=row.get("iev"),
            trend=row.get("trend"),
            rsi=_decimal_or_none(row.get("rsi")),
            gap_pct=_decimal_or_none(row.get("gap_pct")),
            opening_broker_backing_tag=row.get("opening_broker_backing_tag"),
            fvwap_discount_pct=_decimal_or_none(row.get("fvwap_discount_pct")),
        )
        for row in data.get("confirmations", [])
    ]

    csv_store = IntradayConfirmationCsvStore(journal_path)
    count = csv_store.append(entries)

    if count == 0:
        typer.echo(
            f"Already logged for {confirmed_at} — no new rows added ({journal_path})"
        )
    else:
        # Dual-write to unified trades.jsonl
        jsonl_store = TradeJournalJsonlWriter(journal_path.parent / "trades.jsonl")
        for entry in entries:
            jsonl_store.append(intraday_entry_to_record(entry))
        typer.echo(f"Logged {count} confirmation(s) for {confirmed_at} → {journal_path}")


def confirm_log(
    confirmation: Annotated[
        Optional[Path],
        typer.Option(
            "--confirmation",
            help="Path to confirmation sidecar JSON",
        ),
    ] = None,
    journal: Annotated[
        Optional[Path],
        typer.Option(
            "--journal",
            help="Path to intraday confirmation CSV journal",
        ),
    ] = None,
) -> None:
    """
    Append the latest `saham trade confirm` result to the intraday confirmation journal.
    """
    _confirm_log_impl(
        confirmation_path=confirmation or DEFAULT_CONFIRMATION_PATH,
        journal_path=journal or DEFAULT_CONFIRMATION_JOURNAL_PATH,
    )


def confirm_review(
    journal: Annotated[
        Optional[Path],
        typer.Option(
            "--journal",
            help="Path to intraday confirmation CSV journal",
        ),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """
    Review logged intraday confirmation decisions by decision and context buckets.
    """
    from src.application.services.intraday_confirmation_journal import (
        IntradayConfirmationJournalService,
    )
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )

    journal_path = journal or DEFAULT_CONFIRMATION_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    if not journal_path.exists():
        typer.echo(
            f"No confirmation journal found at '{journal_path}'.\n"
            "Run `saham trade log intraday` after confirming opens first.",
            err=True,
        )
        raise typer.Exit(1)

    store = IntradayConfirmationCsvStore(journal_path)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    service = IntradayConfirmationJournalService(store=store, repository=repository)
    report = service.review()
    display_intraday_review(report, journal_path)


def confirm_outcome(
    ticker: Annotated[str, typer.Argument(help="Ticker to update (e.g. BBCA)")],
    entry: Annotated[
        float,
        typer.Option("--entry", help="Actual executed entry price", min=0.0001),
    ],
    exit_price: Annotated[
        float,
        typer.Option("--exit", help="Actual executed exit price", min=0.0001),
    ],
    result: Annotated[
        str,
        typer.Option("--result", help="Outcome label: target, stop, manual, breakeven"),
    ] = "manual",
    confirmed_date: Annotated[
        Optional[str],
        typer.Option("--date", help="Confirmation date YYYY-MM-DD"),
    ] = None,
    notes: Annotated[
        Optional[str],
        typer.Option("--notes", help="Optional execution notes"),
    ] = None,
    journal: Annotated[
        Optional[Path],
        typer.Option(
            "--journal",
            help="Path to intraday confirmation CSV journal",
        ),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """
    Record actual trade outcome for a logged intraday confirmation.
    """
    from src.application.services.intraday_confirmation_journal import (
        IntradayConfirmationJournalService,
    )
    from src.infrastructure.persistence.intraday_confirmation_csv import (
        IntradayConfirmationCsvStore,
    )

    valid_results = {"target", "stop", "manual", "breakeven"}
    outcome_result = result.lower()
    if outcome_result not in valid_results:
        typer.echo(
            f"Error: --result must be one of: {', '.join(sorted(valid_results))}",
            err=True,
        )
        raise typer.Exit(1)

    journal_path = journal or DEFAULT_CONFIRMATION_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH
    if not journal_path.exists():
        typer.echo(
            f"No confirmation journal found at '{journal_path}'.\n"
            "Run `saham trade log intraday` first.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        target_date = (
            date.fromisoformat(confirmed_date) if confirmed_date else date.today()
        )
    except ValueError:
        typer.echo("Error: --date must use YYYY-MM-DD format.", err=True)
        raise typer.Exit(1)

    store = IntradayConfirmationCsvStore(journal_path)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    service = IntradayConfirmationJournalService(store=store, repository=repository)
    updated, outcome_r = service.record_outcome(
        confirmed_at=target_date,
        ticker=ticker.upper(),
        actual_entry_price=Decimal(str(entry)),
        actual_exit_price=Decimal(str(exit_price)),
        outcome_result=outcome_result,
        notes=notes,
    )

    if not updated:
        typer.echo(
            f"No logged confirmation found for {ticker.upper()} on {target_date}.",
            err=True,
        )
        raise typer.Exit(1)

    r_label = f"{outcome_r:+.2f}R" if outcome_r is not None else "N/A"
    typer.echo(
        f"Recorded outcome for {ticker.upper()} on {target_date}: "
        f"{outcome_result} | entry={entry:,.0f} exit={exit_price:,.0f} | R={r_label}"
    )


def intraday_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached'"),
    ] = None,
    start: Annotated[
        str,
        typer.Option("--start", help="Simulation start date YYYY-MM-DD"),
    ] = APP_CFG.backtest.start_date,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Simulation end date YYYY-MM-DD"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = APP_CFG.trading.capital,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade", min=0.01),
    ] = APP_CFG.swing.risk_pct,
    max_daily_positions: Annotated[
        int,
        typer.Option("--max-daily-positions", help="Max simultaneous trades per day", min=1),
    ] = 3,
    max_stop: Annotated[
        Optional[float],
        typer.Option("--max-stop", help="Max allowed stop distance; defaults to pre-open config", min=0.005),
    ] = None,
    cost_bps: Annotated[
        float,
        typer.Option("--cost-bps", help="Transaction cost in basis points per side", min=0),
    ] = APP_CFG.backtest.cost_bps,
    include_wait: Annotated[
        bool,
        typer.Option("--include-wait/--no-include-wait", help="Treat WAIT decisions as ENTER"),
    ] = False,
    atr_mult: Annotated[
        Optional[float],
        typer.Option("--atr-mult", help="ATR multiplier for stop distance; defaults to pre-open config", min=0.1),
    ] = None,
    rsi_overbought: Annotated[
        Optional[float],
        typer.Option("--rsi-overbought", help="RSI threshold for BEARISH classification; defaults to pre-open config"),
    ] = None,
    iev_top_n: Annotated[
        int,
        typer.Option("--iev-top-n", help="IEV snapshots filter top-N movers limit", min=1),
    ] = 5,
    show_trades: Annotated[
        int,
        typer.Option("--show-trades", help="Number of recent trades to display", min=0),
    ] = 20,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Daily-OHLC proxy simulation of the intraday pre-open workflow.

    This is not an exact intraday replay. It uses candle.open as the entry
    proxy, same-day high/low/close for exits, and applies saved IEV snapshots
    only on dates where they exist.
    """
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as exc:
        typer.echo(f"Error: invalid date format — {exc}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to backtest. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    po_config = load_pre_open_screen_config()
    resolved_max_stop = Decimal(str(max_stop)) if max_stop is not None else po_config.max_stop_pct
    resolved_atr_mult = (
        Decimal(str(atr_mult)) if atr_mult is not None else po_config.atr_multiplier
    )
    resolved_rsi_overbought = (
        Decimal(str(rsi_overbought))
        if rsi_overbought is not None
        else po_config.rsi_overbought_threshold
    )

    typer.echo(
        f"Intraday proxy simulation: {len(ticker_list)} tickers | "
        f"{start_date} to {end_date} | "
        f"max_daily={max_daily_positions} | "
        f"include_wait={include_wait}",
        err=True,
    )

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry(
        broker_repository=broker_repo,
        market_repository=market_repo,
    )

    from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
    iev_repo = SQLiteIEVRepository(resolved_db)
    coverage = iev_repo.get_coverage()
    if coverage["total_dates"] > 0:
        typer.echo(
            f"IEV snapshots: {coverage['total_dates']} days "
            f"({coverage['first_date']} → {coverage['last_date']}) — "
            f"top-{iev_top_n} filter will be applied where available.",
            err=True,
        )
    else:
        typer.echo(
            "No IEV snapshots found. Screening full universe each day. "
            "Run 'saham fetch iev' at 08:50 WIB to start collecting.",
            err=True,
        )
        iev_repo = None

    use_case = IntradayBacktestUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        indicator_registry=registry,
        iev_repository=iev_repo,
    )

    try:
        response = use_case.execute(IntradayBacktestRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            max_daily_positions=max_daily_positions,
            max_stop_pct=resolved_max_stop,
            cost_bps=Decimal(str(cost_bps)),
            include_wait=include_wait,
            atr_multiplier=resolved_atr_mult,
            rsi_overbought_threshold=resolved_rsi_overbought,
            atr_range_cap_min=po_config.atr_range_cap_min,
            atr_range_cap_max=po_config.atr_range_cap_max,
            broker_backing_window_days=po_config.broker_backing_window_days,
            broker_backing_threshold=po_config.broker_backing_threshold,
            fvwap_period=po_config.fvwap_period,
            history_days=po_config.history_days,
            iev_top_n=iev_top_n,
        ))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        import json as _json
        typer.echo(_json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "intraday_proxy_simulation",
                "start_date": response.start_date.isoformat(),
                "end_date": response.end_date.isoformat(),
                "initial_capital": str(response.initial_capital),
                "cost_bps": str(response.cost_bps),
                "include_wait": response.include_wait,
                "final_equity": str(response.final_equity),
                "total_return_pct": response.total_return_pct,
                "max_drawdown_pct": response.max_drawdown_pct,
                "trade_count": response.trade_count,
                "win_rate_pct": response.win_rate_pct,
                "avg_trade_return_pct": response.avg_trade_return_pct,
                "profit_factor": response.profit_factor,
                "expectancy_pct": response.expectancy_pct,
                "avg_r_multiple": response.avg_r_multiple,
                "exit_reason_counts": response.exit_reason_counts,
                "decisions": response.decisions,
                "by_opening_broker_backing_tag": [
                    {**r, "total_pnl": str(r["total_pnl"])} for r in response.by_opening_broker_backing_tag
                ],
                "by_fvwap_sign": [
                    {**r, "total_pnl": str(r["total_pnl"])} for r in response.by_fvwap_sign
                ],
                "by_rsi_bucket": [
                    {**r, "total_pnl": str(r["total_pnl"])} for r in response.by_rsi_bucket
                ],
                "by_ticker": [
                    {**r, "total_pnl": str(r["total_pnl"])} for r in response.by_ticker
                ],
                "trades": [t.to_dict() for t in response.trades],
                "warnings": response.warnings,
            },
            indent=2,
            default=str,
        ))
        return

    from src.adapters.cli.trade_intraday_backtest_display import display_intraday_backtest
    display_intraday_backtest(response, show_trades=show_trades)
