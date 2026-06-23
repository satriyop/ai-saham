"""
CLI commands for the opening session learning loop.

Commands (all under `saham learn`):
  snapshot  — 08:57 WIB: NCP-locked pre-open screener capture
  track     — 09:00–09:30 WIB: 5-min orderbook loop for all screened tickers
  grade     — 09:35+ WIB: deterministic accuracy report (no network)
  tune      — 09:40+ WIB: DeepSeek AI config recommendations
  prompt    — on-demand: copy-paste AI prompt for any AI assistant

All commands accept --date YYYY-MM-DD for retrospective runs
and --force to bypass IDX trading-hour guards.

Layer: Adapter
"""

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import APP_CFG

OPENING_DATA_DIR = Path(APP_CFG.storage.opening_data_dir)
DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_SESSION_FILE = Path(APP_CFG.storage.stockbit_session_file)
DEFAULT_PRE_OPEN_CONFIG = Path(APP_CFG.storage.pre_open_config)

learn_app = typer.Typer(
    name="learn",
    help="Learning loop — snapshot, track, grade, prompt, and tune opening sessions.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _today_dir(run_date: date | None = None) -> Path:
    d = run_date or datetime.now(IDX_TIMEZONE).date()
    return OPENING_DATA_DIR / d.strftime("%Y%m%d")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        typer.echo(f"Invalid date format: {s} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)


# ── snapshot ──────────────────────────────────────────────────────────────────


@learn_app.command("snapshot")
def snapshot(
    force: Annotated[
        bool, typer.Option("--force", help="Run outside 08:55–09:00 WIB window")
    ] = False,
    date_str: Annotated[Optional[str], typer.Option("--date", help="Date YYYY-MM-DD")] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    config_path: Annotated[Optional[Path], typer.Option("--config", "-c")] = None,
    headless: Annotated[bool, typer.Option("--headless/--no-headless")] = True,
) -> None:
    """
    Capture NCP-locked pre-open screener signals at 08:57 WIB.

    Runs the full screener pipeline and saves all prediction signals to
    data/opening/YYYYMMDD/snapshot.json for later accuracy grading.

    Also writes the standard .last-session.json sidecar so `saham trade confirm` still works.

    Examples:
        saham learn snapshot               # live at 08:57 WIB
        saham learn snapshot --force       # manual dry-run anytime
        saham learn snapshot --date 2026-06-18 --force
    """
    run_date = _parse_date(date_str)
    resolved_db = db_path or DEFAULT_DB_PATH
    resolved_config = config_path or DEFAULT_PRE_OPEN_CONFIG

    now = datetime.now(IDX_TIMEZONE)
    hour, minute = now.hour, now.minute
    in_window = (hour == 8 and minute >= 55) or (hour == 9 and minute == 0)

    if not force and not in_window:
        typer.echo(
            f"Not in NCP window (08:55–09:00 WIB). Current: {now.strftime('%H:%M')} WIB.\n"
            "Use --force to run outside the window.",
            err=True,
        )
        raise typer.Exit(1)

    # Secondary check via Stockbit market-time API: warn if not in Pre-Open session
    # (catches IDX holidays where in_window is true but market is closed).
    if not force:
        try:
            from pathlib import Path as _Path

            from src.infrastructure.browser.stockbit_market_time import (
                StockbitMarketTimeProvider,
            )

            _mstatus = None
            if _Path(APP_CFG.storage.stockbit_profile_dir).exists():
                from src.infrastructure.browser.playwright_stockbit import (
                    StockbitPlaywrightBrokerProvider,
                )

                _bp = StockbitPlaywrightBrokerProvider()
                if _bp.is_authenticated():
                    _mstatus = StockbitMarketTimeProvider(broker_provider=_bp).get_status()
            if _mstatus and _mstatus.source == "stockbit" and not _mstatus.is_pre_open:
                typer.echo(
                    f"Warning: Stockbit reports session='{_mstatus.session_name}' "
                    f"(status={_mstatus.status}), not Pre-Open. "
                    "This may be an IDX holiday. Use --force to proceed anyway.",
                    err=True,
                )
                raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception:
            pass  # Never block on market-status probe failure

    try:
        from src.adapters.cli.screen_pre_open_commands import (
            _load_config,
            _playwright_available,
        )
        from src.application.services.bootstrap import create_indicator_registry
        from src.application.use_case.opening_snapshot import (
            OpeningSnapshotRequest,
            OpeningSnapshotUseCase,
        )
        from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider
        from src.infrastructure.browser.stockbit_ticker_notation import (
            StockbitTickerNotationProvider,
        )
        from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
        from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
        from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    if not _playwright_available() or not DEFAULT_SESSION_FILE.exists():
        typer.echo("No Playwright session. Run: saham fetch stockbit login", err=True)
        raise typer.Exit(1)

    config = _load_config(resolved_config, {})
    repository = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry(
        broker_repository=broker_repo, market_repository=repository
    )
    browser = PlaywrightStockbitProvider(
        profile_dir=Path(APP_CFG.storage.stockbit_profile_dir), headless=headless
    )

    # Load today's NCP-locked IEP values for enrichment
    iev_repo = SQLiteIEVRepository(resolved_db)
    today_date = run_date or now.date()
    iep_lookup: dict[str, int] = {}
    try:
        ncp_snaps = iev_repo.get_ncp_snapshot(snapshot_date=today_date)
        iep_lookup = {s.ticker: s.iep for s in ncp_snaps if s.iep}
    except Exception:
        pass

    notation_provider = StockbitTickerNotationProvider(broker_provider=None, db_path=resolved_db)
    use_case = OpeningSnapshotUseCase(
        browser=browser,
        repository=repository,
        registry=registry,
        broker_repository=broker_repo,
        ticker_notation_provider=notation_provider,
    )

    typer.echo(f"Running NCP-locked screener snapshot at {now.strftime('%H:%M:%S')} WIB...")
    result = use_case.execute(
        OpeningSnapshotRequest(
            config=config,
            run_date=run_date,
            iep_lookup=iep_lookup,
        )
    )

    # Sidecar already written inside PreOpenScreenUseCase; notify user of output path.
    out_dir = _today_dir(run_date)
    n = len(result.get("candidates", []))
    typer.echo(f"Saved {n} candidates → {out_dir}/snapshot.json")
    for c in result.get("candidates", []):
        verdict = c.get("verdict", "?")
        typer.echo(
            f"  {c['ticker']:8s}  {verdict:5s}  "
            f"trend={c.get('trend', '?'):8s}  IEP={c.get('iep', '?')}"
        )


# ── track ─────────────────────────────────────────────────────────────────────


@learn_app.command("track")
def track(
    force: Annotated[
        bool, typer.Option("--force", help="Run single snapshot immediately (bypass window)")
    ] = False,
    tickers: Annotated[
        Optional[list[str]], typer.Argument(help="Explicit tickers (overrides snapshot)")
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

    Reads tickers from today's snapshot.json. Saves track_HHMM.json per interval.
    Full order book depth (bid_pressure_ratio, fnet_intraday) is always captured.

    Use --force with explicit tickers for manual dry-runs outside market hours.
    Use --broker-confirm to embed institutional broker absorption data per tick interval.

    Examples:
        saham learn track                               # live 09:00–09:30 loop
        saham learn track --force BBCA BBRI BMRI       # manual dry-run
        saham learn track --broker-confirm              # with broker attribution
    """
    run_date = _parse_date(date_str)

    # Resolve tickers
    if tickers:
        resolved_tickers = list(tickers)
    else:
        snap_path = _today_dir(run_date) / "snapshot.json"
        if not snap_path.exists():
            typer.echo(
                f"No snapshot found at {snap_path}. Run `saham learn snapshot` first.", err=True
            )
            raise typer.Exit(1)
        with open(snap_path) as f:
            snap = json.load(f)
        resolved_tickers = [c["ticker"] for c in snap.get("candidates", [])]

    if not resolved_tickers:
        typer.echo("No tickers to track.", err=True)
        raise typer.Exit(1)

    try:
        from src.application.use_case.opening_track import OpeningTrackRequest, OpeningTrackUseCase
        from src.infrastructure.browser.playwright_stockbit import PlaywrightStockbitProvider
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    if not DEFAULT_SESSION_FILE.exists():
        typer.echo("No Stockbit session. Run: saham fetch stockbit login", err=True)
        raise typer.Exit(1)

    browser = PlaywrightStockbitProvider(
        profile_dir=Path(APP_CFG.storage.stockbit_profile_dir), headless=headless
    )

    # Optionally wire broker confirmation provider
    running_trade_provider = None
    institutional_codes: frozenset[str] = frozenset()
    if broker_confirm:
        try:
            import yaml

            from src.infrastructure.browser.playwright_stockbit import (
                StockbitPlaywrightBrokerProvider,
            )
            from src.infrastructure.browser.stockbit_running_trade import (
                StockbitRunningTradeProvider,
            )

            broker_provider = StockbitPlaywrightBrokerProvider()
            if broker_provider.is_authenticated():
                running_trade_provider = StockbitRunningTradeProvider(
                    broker_provider=broker_provider
                )
                with open("config/stockbit.yaml") as f:
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

    # Always wire order book provider — full depth replaces naive top-of-book bid_pressure
    order_book_provider = None
    try:
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        from src.infrastructure.browser.stockbit_order_book import StockbitOrderBookProvider

        ob_broker = StockbitPlaywrightBrokerProvider()
        if ob_broker.is_authenticated():
            order_book_provider = StockbitOrderBookProvider(broker_provider=ob_broker)
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

    out_dir = _today_dir(run_date)
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


# ── grade ─────────────────────────────────────────────────────────────────────


@learn_app.command("grade")
def grade(
    date_str: Annotated[Optional[str], typer.Option("--date")] = None,
) -> None:
    """
    Compute deterministic accuracy report from today's snapshot + track data.

    Requires: snapshot.json and at least one track_*.json from today.

    Examples:
        saham learn grade
        saham learn grade --date 2026-06-17
    """
    run_date = _parse_date(date_str)

    try:
        from src.application.use_case.opening_grade import compute_grade
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    try:
        result = compute_grade(run_date)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    out_dir = _today_dir(run_date)
    typer.echo(f"Grade saved → {out_dir}/grade.json + grade.md")
    typer.echo("")
    typer.echo(f"  Entry range hit rate:   {_pct(result.get('entry_range_hit_rate'))}")
    typer.echo(f"  Trend accuracy T+5m:    {_pct(result.get('trend_accuracy_T5'))}")
    typer.echo(f"  Trend accuracy T+30m:   {_pct(result.get('trend_accuracy_T30'))}")
    typer.echo(f"  Clean trade rate:       {_pct(result.get('clean_trade_rate'))}")
    typer.echo("")
    for verdict in ("PRIME", "WATCH", "SKIP"):
        v = result.get("by_verdict", {}).get(verdict, {})
        if v.get("count", 0) > 0:
            typer.echo(
                f"  {verdict:5s}  n={v['count']}  "
                f"entry_hit={_pct(v.get('entry_range_hit_rate'))}  "
                f"clean={_pct(v.get('clean_trade_rate'))}"
            )

    # Show broker confirmation data if present (--broker-confirm was used during track)
    broker_tickers = [
        t
        for t in result.get("per_ticker", [])
        if t.get("institutional_absorption_rate") is not None
    ]
    if broker_tickers:
        typer.echo("")
        typer.echo("  Broker Confirmation (institutional absorption):")
        for t in broker_tickers:
            side = t.get("broker_dominant_side", "?")
            abs_rate = t.get("institutional_absorption_rate")
            typer.echo(f"    {t['ticker']:8s}  {side:7s}  abs={_pct(abs_rate)}")

    # Show order book depth data (always captured when session is authenticated)
    ob_tickers = [t for t in result.get("per_ticker", []) if t.get("bid_pressure_T0") is not None]
    if ob_tickers:
        typer.echo("")
        typer.echo("  Order Book Depth (bid pressure ratio + live F.Net):")
        for t in ob_tickers:
            bp_t0 = t.get("bid_pressure_T0")
            bp_t5 = t.get("bid_pressure_T5")
            momentum = t.get("bid_momentum")
            fnet = t.get("fnet_latest")
            fnet_str = f"{fnet / 1e9:+.1f}B" if fnet is not None else "?"
            momentum_str = f"{momentum:+.3f}" if momentum is not None else "?"
            bp_t5_str = _pct(bp_t5) if bp_t5 is not None else "?"
            typer.echo(
                f"    {t['ticker']:8s}  bp_T0={_pct(bp_t0)}  bp_T5={bp_t5_str}"
                f"  Δ={momentum_str}  F.Net={fnet_str}"
            )


# ── tune ──────────────────────────────────────────────────────────────────────


@learn_app.command("tune")
def tune(
    date_str: Annotated[Optional[str], typer.Option("--date")] = None,
    api_key: Annotated[
        Optional[str], typer.Option("--api-key", help="DeepSeek API key (overrides env)")
    ] = None,
    allow_invalid_snapshot: Annotated[
        bool,
        typer.Option(
            "--allow-invalid-snapshot",
            help="Allow AI tuning from low-confidence or out-of-window snapshot data",
        ),
    ] = False,
) -> None:
    """
    Call DeepSeek AI with today's accuracy grade and save config recommendations.

    Requires: grade.json from today (run `saham learn grade` first).
    Reads DEEPSEEK_API_KEY from environment if --api-key not provided.

    Saves: data/opening/YYYYMMDD/tune.json + tune.md

    Examples:
        saham learn tune
        saham learn tune --date 2026-06-17
    """
    run_date = _parse_date(date_str)
    resolved_key = api_key or os.environ.get("DEEPSEEK_API_KEY")

    if not resolved_key:
        typer.echo("No DeepSeek API key. Set DEEPSEEK_API_KEY or pass --api-key.", err=True)
        raise typer.Exit(1)

    try:
        from src.application.use_case.opening_tune import OpeningTuneRequest, OpeningTuneUseCase
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    use_case = OpeningTuneUseCase()
    typer.echo("Calling DeepSeek for config recommendations...")

    result = use_case.execute(
        OpeningTuneRequest(
            run_date=run_date,
            deepseek_api_key=resolved_key,
            allow_invalid_snapshot=allow_invalid_snapshot,
        )
    )

    if result.get("skipped"):
        typer.echo(f"Skipped: {result.get('reason')}", err=True)
        raise typer.Exit(1)

    out_dir = _today_dir(run_date)
    typer.echo(f"Saved → {out_dir}/tune.json + tune.md  ({result.get('tokens_used', 0)} tokens)")
    if result.get("summary"):
        typer.echo(f"\nSummary: {result['summary']}")
    if result.get("top_finding"):
        typer.echo(f"Top finding: {result['top_finding']}")

    recs = result.get("config_recommendations", {})
    if recs:
        typer.echo("\nRecommended changes:")
        for file_key, params in recs.items():
            typer.echo(f"  [{file_key}]")
            for param, change in params.items():
                typer.echo(
                    f"    {param}: {change.get('current')} → {change.get('suggested')}"
                    f"  # {change.get('reason', '')}"
                )


# ── prompt ────────────────────────────────────────────────────────────────────


@learn_app.command("prompt")
def prompt(
    date_str: Annotated[Optional[str], typer.Option("--date")] = None,
    print_output: Annotated[bool, typer.Option("--print", help="Print prompt to stdout")] = False,
) -> None:
    """
    Generate a copy-pasteable AI prompt from today's session data.

    Includes screener predictions, actual price outcomes, and accuracy metrics
    in a format ready to paste into Claude, ChatGPT, or any AI assistant.

    Saves: data/opening/YYYYMMDD/prompt.md

    Examples:
        saham learn prompt
        saham learn prompt --print | pbcopy   # copy to clipboard (macOS)
    """
    run_date = _parse_date(date_str)

    try:
        from src.application.use_case.opening_prompt import build_prompt
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    try:
        content = build_prompt(run_date)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    out_dir = _today_dir(run_date)
    typer.echo(f"Prompt saved → {out_dir}/prompt.md")

    if print_output:
        typer.echo(content)


# ── helpers ───────────────────────────────────────────────────────────────────


def _pct(v) -> str:
    return f"{v * 100:.1f}%" if v is not None else "N/A"
