"""CLI commands for active intraday trading workflows. Layer: Adapter."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_intraday_confirmation_journal_actions import (
    run_confirm_outcome,
    run_confirm_review,
)
from src.adapters.cli.trade_intraday_display import (
    display_confirmations,
    format_opening_observation_status,
    format_ticker_preview,
)
from src.application.services.intraday_confirmation_session_store import (
    load_intraday_confirmation_candidates,
    load_intraday_confirmation_tickers,
    load_opening_prices_from_track_file,
    load_pre_open_market_regime,
    write_intraday_confirmation_sidecar,
)
from src.application.use_case.confirm_intraday_open_use_case import (
    ConfirmIntradayOpenRequest,
    ConfirmIntradayOpenUseCase,
)
from src.application.use_case.log_intraday_confirmation_use_case import (
    LogIntradayConfirmationRequest,
    LogIntradayConfirmationUseCase,
)
from src.application.use_case.resolve_opening_prices_use_case import (
    OpeningPriceObservation,
    ResolveOpeningPricesRequest,
    ResolveOpeningPricesUseCase,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config
from src.infrastructure.persistence.intraday_confirmation_csv import (
    IntradayConfirmationCsvStore,
)
from src.infrastructure.persistence.trade_journal_jsonl_writer import (
    TradeJournalJsonlWriter,
)

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_SIDECAR_PATH = Path(APP_CFG.storage.intraday_sidecar)
DEFAULT_CONFIRMATION_PATH = Path(APP_CFG.storage.intraday_confirmation)
DEFAULT_CONFIRMATION_JOURNAL_PATH = Path(APP_CFG.storage.intraday_confirmation_journal)


def confirm_open(
    opening_json: Annotated[
        Optional[str], typer.Option("--opening-json", help="Manual prices JSON")
    ] = None,
    track_file: Annotated[
        Optional[Path], typer.Option("--track-file", help="Track file for offline prices")
    ] = None,
    session: Annotated[
        Optional[Path], typer.Option("--session", help="Pre-open sidecar JSON path")
    ] = None,
    output: Annotated[
        Optional[Path], typer.Option("--output", help="Confirmation output path")
    ] = None,
    max_stop: Annotated[
        float, typer.Option("--max-stop", help="Max stop decimal, 0.07=7%")
    ] = 0.07,
    headless: Annotated[
        bool, typer.Option("--headless/--no-headless", help="Headless browser for auto-confirm")
    ] = True,
) -> None:
    sidecar_path = session or DEFAULT_SIDECAR_PATH
    output_path = output or DEFAULT_CONFIRMATION_PATH
    if not sidecar_path.exists():
        typer.echo(
            f"No session sidecar at '{sidecar_path}'.\n"
            "Run `saham screen pre-open` first.", err=True,
        )
        raise typer.Exit(1)
    manual_prices: dict[str, Decimal] = {}
    if opening_json:
        try:
            raw_opening = json.loads(opening_json)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid --opening-json: {e}", err=True)
            raise typer.Exit(1)
        if not isinstance(raw_opening, dict):
            typer.echo("Error: --opening-json must be a JSON object.", err=True)
            raise typer.Exit(1)
        try:
            manual_prices = {
                str(t.upper()): Decimal(str(p))
                for t, p in raw_opening.items() if p is not None
            }
        except Exception as e:
            typer.echo(f"Error: opening prices must be numeric: {e}", err=True)
            raise typer.Exit(1)
    if max_stop <= 0:
        typer.echo("Error: --max-stop must be positive.", err=True)
        raise typer.Exit(1)
    screened_at, tickers = load_intraday_confirmation_tickers(sidecar_path)
    track_prices: dict[str, OpeningPriceObservation] = {}
    if track_file:
        if not track_file.exists():
            typer.echo(f"Error: Track file not found at '{track_file}'", err=True)
            raise typer.Exit(1)
        try:
            track_prices = load_opening_prices_from_track_file(track_file, tickers)
        except Exception as e:
            typer.echo(f"Error parsing track file '{track_file}': {e}", err=True)
            raise typer.Exit(1)
    running_trade_provider = None
    order_book_provider = None
    missing_resolved = [
        t for t in tickers if t not in manual_prices and t not in track_prices
    ]
    auto_needed = bool(missing_resolved) if not track_file else False
    typer.echo(
        f"Confirming {len(tickers)} pre-open candidate(s) "
        f"from {sidecar_path} for {screened_at}."
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
            "Tip: pass --opening-json or --track-file "
            "to skip browser-backed auto resolution."
        )
        try:
            from src.infrastructure.browser.stockbit_order_book import (
                StockbitOrderBookProvider,
            )
            from src.infrastructure.browser.stockbit_running_trade import (
                StockbitRunningTradeProvider,
            )
            from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session
            _trade_session = get_stockbit_session()
            if not _trade_session or not _trade_session.authenticated:
                typer.echo(
                    "No authenticated Stockbit profile for auto confirm. "
                    "Run `saham fetch stockbit login` or "
                    "pass --opening-json / --track-file.", err=True,
                )
                raise typer.Exit(1)
            api = _trade_session.api_client
            running_trade_provider = StockbitRunningTradeProvider(api_client=api)
            order_book_provider = StockbitOrderBookProvider(api_client=api)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(
                f"Auto confirm setup failed: {e}. "
                "Pass --opening-json or --track-file to confirm manually.", err=True,
            )
            raise typer.Exit(1)
    resolver = ResolveOpeningPricesUseCase(
        running_trade_provider=running_trade_provider,
        order_book_provider=order_book_provider,
        on_observation=lambda i, t, o: typer.echo(
            format_opening_observation_status(i, t, o)
        ),
    )
    observations = resolver.execute(
        ResolveOpeningPricesRequest(
            tickers=tickers, run_date=screened_at,
            manual_prices=manual_prices, track_prices=track_prices,
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
        t: o.price for t, o in observations.items() if o.price is not None
    }
    screened_at, candidates, extras = load_intraday_confirmation_candidates(
        sidecar_path, opening_prices, observations,
    )
    po_config = load_pre_open_screen_config()
    regime_val, regime_warning = load_pre_open_market_regime(sidecar_path)
    if regime_warning:
        typer.echo(regime_warning, err=True)
        regime_val = "RISK_OFF"
    use_case = ConfirmIntradayOpenUseCase()
    result = use_case.execute(
        ConfirmIntradayOpenRequest(
            candidates=candidates, run_date=screened_at,
            max_stop_pct=Decimal(str(max_stop)),
            tick_friction_gate=po_config.tick_friction_gate,
            min_target_ticks=po_config.min_target_ticks,
            min_stop_ticks=po_config.min_stop_ticks, regime=regime_val,
            regime_gate_enabled=po_config.regime_gate_enabled,
            tighten_in_regimes=tuple(po_config.tighten_in_regimes),
            gap_pct_tightening_factor=Decimal(str(po_config.gap_pct_tightening_factor)),
            require_backed_in_weak=po_config.require_backed_in_weak,
        )
    )
    display_confirmations(
        result.confirmations, result.confirmed_date,
        result.max_stop_pct, extras=extras,
    )
    write_intraday_confirmation_sidecar(
        result.confirmations, result.confirmed_date,
        result.max_stop_pct, output_path,
    )


def _confirm_log_impl(confirmation_path: Path, journal_path: Path) -> None:
    confirm_log(confirmation=confirmation_path, journal=journal_path)


def confirm_log(
    confirmation: Annotated[
        Optional[Path], typer.Option("--confirmation", help="Confirmation sidecar path")
    ] = None,
    journal: Annotated[
        Optional[Path], typer.Option("--journal", help="Intraday CSV journal")
    ] = None,
) -> None:
    confirmation_path = confirmation or DEFAULT_CONFIRMATION_PATH
    journal_path = journal or DEFAULT_CONFIRMATION_JOURNAL_PATH
    csv_store = IntradayConfirmationCsvStore(journal_path)
    jsonl_store = TradeJournalJsonlWriter(confirmation_path.parent / "trades.jsonl")
    use_case = LogIntradayConfirmationUseCase(
        confirmation_store=csv_store, trade_journal_store=jsonl_store,
    )
    try:
        response = use_case.execute(
            LogIntradayConfirmationRequest(
                confirmation_path=confirmation_path, journal_path=journal_path,
            )
        )
    except FileNotFoundError:
        typer.echo(
            f"No confirmation sidecar at '{confirmation_path}'.\n"
            "Run `saham trade confirm` first.", err=True,
        )
        raise typer.Exit(1)
    except json.JSONDecodeError:
        typer.echo(
            f"Error: invalid confirmation sidecar at '{confirmation_path}'.", err=True,
        )
        raise typer.Exit(1)
    if response.duplicate:
        typer.echo(
            f"Already logged for {response.confirmed_at} — "
            f"no new rows added ({response.journal_path})"
        )
    else:
        typer.echo(
            f"Logged {response.logged_count} confirmation(s) "
            f"for {response.confirmed_at} → {response.journal_path}"
        )


def confirm_review(
    journal: Annotated[
        Optional[Path], typer.Option("--journal", help="Intraday CSV journal")
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    run_confirm_review(
        journal_path=journal or DEFAULT_CONFIRMATION_JOURNAL_PATH,
        db_path=db_path or DEFAULT_DB_PATH,
    )


def confirm_outcome(
    ticker: Annotated[str, typer.Argument(help="Ticker to update")],
    entry: Annotated[float, typer.Option("--entry", help="Actual entry price", min=0.0001)],
    exit_price: Annotated[float, typer.Option("--exit", help="Actual exit price", min=0.0001)],
    result: Annotated[
        str, typer.Option("--result", help="Outcome: target/stop/manual/breakeven")
    ] = "manual",
    confirmed_date: Annotated[
        Optional[str], typer.Option("--date", help="Date YYYY-MM-DD")
    ] = None,
    notes: Annotated[
        Optional[str], typer.Option("--notes", help="Execution notes")
    ] = None,
    journal: Annotated[
        Optional[Path], typer.Option("--journal", help="Intraday CSV journal")
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    run_confirm_outcome(
        ticker=ticker,
        entry=entry,
        exit_price=exit_price,
        result=result,
        confirmed_date=confirmed_date,
        notes=notes,
        journal_path=journal or DEFAULT_CONFIRMATION_JOURNAL_PATH,
        db_path=db_path or DEFAULT_DB_PATH,
    )
