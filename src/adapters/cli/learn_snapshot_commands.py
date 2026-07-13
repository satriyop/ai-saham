"""
Snapshot command for the opening session learning loop.

Captures NCP-locked pre-open screener signals at 08:57 WIB.

Layer: Adapter
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.learn_command_paths import (
    DEFAULT_DB_PATH,
    DEFAULT_PRE_OPEN_CONFIG,
    DEFAULT_SESSION_FILE,
    opening_day_dir,
    parse_learn_date,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import APP_CFG


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
    run_date = parse_learn_date(date_str)
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

    if not force:
        try:
            from src.application.services.stockbit_session import get_stockbit_session
            from src.infrastructure.browser.stockbit_market_time import StockbitMarketTimeProvider

            _mstatus = None
            _mtime_session = get_stockbit_session()
            if _mtime_session and _mtime_session.authenticated:
                _mstatus = (
                    StockbitMarketTimeProvider(api_client=_mtime_session.api_client).get_status()
                )
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
            pass

    try:
        from src.adapters.cli.screen_pre_open_commands import (
            _playwright_available,
        )
        from src.application.services.bootstrap import create_indicator_registry
        from src.application.use_case.opening_snapshot_use_case import (
            OpeningSnapshotRequest,
            OpeningSnapshotUseCase,
        )
        from src.infrastructure.browser.playwright_stockbit_provider import (
            PlaywrightStockbitProvider,
        )
        from src.infrastructure.browser.stockbit_ticker_notation import (
            StockbitTickerNotationProvider,
        )
        from src.infrastructure.config.pre_open_config import load_pre_open_screen_config
        from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
        from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
        from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
    except ImportError as e:
        typer.echo(f"Import error: {e}", err=True)
        raise typer.Exit(1)

    if not _playwright_available() or not DEFAULT_SESSION_FILE.exists():
        typer.echo("No Playwright session. Run: saham fetch stockbit login", err=True)
        raise typer.Exit(1)

    config = load_pre_open_screen_config(resolved_config)
    repository = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry(
        broker_repository=broker_repo, market_repository=repository
    )
    from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
    api_client = create_stockbit_api_client(
        profile_dir=Path(APP_CFG.storage.stockbit_profile_dir), headless=headless
    )
    browser = PlaywrightStockbitProvider(api_client=api_client)

    iev_repo = SQLiteIEVRepository(resolved_db)
    today_date = run_date or now.date()
    iep_lookup: dict[str, int] = {}
    try:
        ncp_snaps = iev_repo.get_ncp_snapshot(snapshot_date=today_date)
        iep_lookup = {s.ticker: s.iep for s in ncp_snaps if s.iep}
    except Exception:
        pass

    notation_provider = StockbitTickerNotationProvider(api_client=None, db_path=resolved_db)
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

    out_dir = opening_day_dir(run_date)
    n = len(result.get("candidates", []))
    typer.echo(f"Saved {n} candidates → {out_dir}/snapshot.json")
    for c in result.get("candidates", []):
        opening_setup = c.get("opening_setup", "?")
        typer.echo(
            f"  {c['ticker']:8s}  {opening_setup:5s}  "
            f"trend={c.get('trend', '?'):8s}  IEP={c.get('iep', '?')}"
        )
