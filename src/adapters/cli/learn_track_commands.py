"""
Track command for the opening session learning loop.

Tracks orderbook every 5 minutes from 09:00–09:30 WIB for all screened tickers.

Layer: Adapter
"""

import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.learn_command_paths import (
    opening_day_dir,
    parse_learn_date,
)
from src.infrastructure.config.app_config import load_app_config


def track(
    force: Annotated[
        bool, typer.Option("--force", help="Run single snapshot immediately (bypass window)")
    ] = False,
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit tickers (overrides saved observations)"),
    ] = None,
    date_str: Annotated[Optional[str], typer.Option("--date")] = None,
    headless: Annotated[bool, typer.Option("--headless/--no-headless")] = True,
    broker_confirm: Annotated[
        bool,
        typer.Option(
            "--broker-confirm",
            help="Also fetch running-trade ticks for broker confirmation (~2s per ticker)",
        ),
    ] = False,
) -> None:
    """
    Track orderbook every 5 minutes from 09:00–09:30 WIB for all screened tickers.

    Reads tickers from saved pre-open observations (research pre-open capture).
    Saves track_HHMM.json per interval. Full order book depth is always captured.

    Use --force with explicit tickers for manual dry-runs outside market hours.
    Use --broker-confirm to embed institutional broker absorption data per tick interval.

    Examples:
        saham learn track                               # live 09:00–09:30 loop
        saham learn track --force BBCA BBRI BMRI       # manual dry-run
        saham learn track --broker-confirm              # with broker attribution
    """
    cfg = load_app_config()
    run_date = parse_learn_date(date_str)
    db_path = Path(cfg.storage.db_path)

    if tickers:
        resolved_tickers = list(tickers)
    else:
        from src.application.services.pre_open_observation_queries import (
            list_pre_open_tickers,
        )
        from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
            SQLiteCandidateObservationsRepository,
        )

        repo = SQLiteCandidateObservationsRepository(db_path)
        resolved_tickers = list_pre_open_tickers(repo, run_date)
        if not resolved_tickers:
            typer.echo(
                f"No saved pre-open observations for {run_date}. "
                "Run `saham research pre-open capture` first.",
                err=True,
            )
            raise typer.Exit(1)

    if not resolved_tickers:
        typer.echo("No tickers to track.", err=True)
        raise typer.Exit(1)

    try:
        from src.application.use_case.opening_track_use_case import (
            OpeningTrackRequest,
            OpeningTrackUseCase,
        )
        from src.infrastructure.browser.playwright_stockbit_provider import (
            PlaywrightStockbitProvider,
        )
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    resolved_session_file = Path(cfg.storage.stockbit_session_file)
    if not resolved_session_file.exists():
        typer.echo("No Stockbit session. Run: saham fetch stockbit login", err=True)
        raise typer.Exit(1)

    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.composition.stockbit_session_factory import (
        get_stockbit_session as _get_learn_session,
    )
    _stockbit_config = load_stockbit_provider_config()
    _learn_session = _get_learn_session(_stockbit_config)

    from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
    _api_client = (
        _learn_session.api_client if _learn_session else None
    ) or create_stockbit_api_client(
        profile_dir=Path(cfg.storage.stockbit_profile_dir),
        headless=headless,
        stockbit_config=_stockbit_config,
    )

    browser = PlaywrightStockbitProvider(api_client=_api_client, stockbit_config=_stockbit_config)

    running_trade_provider = None
    institutional_codes: frozenset[str] = frozenset()
    if broker_confirm:
        try:
            import yaml

            from src.infrastructure.browser.stockbit_running_trade import (
                StockbitRunningTradeProvider,
            )

            if _learn_session and _learn_session.authenticated:
                running_trade_provider = StockbitRunningTradeProvider(
                    api_client=_learn_session.api_client, stockbit_config=_stockbit_config
                )
                with open(cfg.config_paths.stockbit) as f:
                    stockbit_cfg = yaml.safe_load(f) or {}
                institutional_codes = frozenset(
                    stockbit_cfg.get("broker_codes", {}).get("institutional_proxy", [])
                )
                typer.echo(
                    "Broker confirm enabled — "
                    f"{len(institutional_codes)} institutional codes loaded"
                )
            else:
                typer.echo(
                    "Stockbit session not authenticated — --broker-confirm disabled", err=True
                )
        except Exception as e:
            typer.echo(f"Broker confirm setup failed: {e} — continuing without it", err=True)

    order_book_provider = None
    try:
        from src.infrastructure.browser.stockbit_order_book import StockbitOrderBookProvider

        if _learn_session and _learn_session.authenticated:
            order_book_provider = StockbitOrderBookProvider(
                api_client=_learn_session.api_client, stockbit_config=_stockbit_config
            )
            typer.echo("Order book depth enabled — bid_pressure_ratio + live F.Net per snapshot")
        else:
            typer.echo("Stockbit session not authenticated — order book disabled", err=True)
    except Exception as e:
        typer.echo(f"Order book setup failed: {e} — continuing without it", err=True)

    use_case = OpeningTrackUseCase(
        browser=browser,
        running_trade_provider=running_trade_provider,
        order_book_provider=order_book_provider,
    )

    typer.echo(f"Tracking {len(resolved_tickers)} tickers: {', '.join(resolved_tickers)}")
    if force:
        typer.echo("Force mode — single immediate snapshot")
    else:
        typer.echo("Live mode — looping every 5 min from 09:00–09:30 WIB")

    out_dir = opening_day_dir(run_date)
    out_dir.mkdir(parents=True, exist_ok=True)
    lock_file = out_dir / ".track.lock"
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            os.kill(pid, 0)
            typer.echo(f"saham learn track already running (PID {pid}). Exiting.")
            raise typer.Exit()
        except (ProcessLookupError, PermissionError):
            lock_file.unlink(missing_ok=True)
    lock_file.write_text(str(os.getpid()))
    try:
        snapshots = use_case.execute(
            OpeningTrackRequest(
                tickers=resolved_tickers,
                run_date=run_date,
                force=force,
                broker_confirm=broker_confirm and running_trade_provider is not None,
                institutional_broker_codes=institutional_codes,
            )
        )

        typer.echo(f"Captured {len(snapshots)} snapshots → {out_dir}/track_*.json")
        for snap in snapshots:
            at = snap.get("captured_at", "?")[:19]
            n_ok = sum(1 for v in snap.get("tickers", {}).values() if v and "error" not in v)
            n_broker = sum(
                1
                for v in snap.get("tickers", {}).values()
                if isinstance(v, dict) and v.get("broker_signal")
            )
            n_ob = sum(
                1
                for v in snap.get("tickers", {}).values()
                if isinstance(v, dict) and v.get("order_book")
            )
            extras = [f"ob={n_ob}/{len(resolved_tickers)}"]
            if broker_confirm:
                extras.append(f"broker={n_broker}/{len(resolved_tickers)}")
            typer.echo(f"  {at}  {n_ok}/{len(resolved_tickers)} tickers OK  " + "  ".join(extras))
    finally:
        lock_file.unlink(missing_ok=True)
