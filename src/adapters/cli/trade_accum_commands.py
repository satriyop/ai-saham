"""
CLI implementation for saham trade log/review swing commands.

Public command registration lives in lifecycle routers:
  saham trade log --type swing
  saham trade review swing

Layer: Adapter
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    SwingSetupCatalogConfig,
)
from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.market_context_factory import create_market_context_engine
from src.infrastructure.config.swing_backtest_config import (
    load_swing_backtest_config as _load_swing_backtest_config,
)
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_config
from src.infrastructure.config.ticker_profile_config_loader import (
    create_ticker_profile_classifier,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

_SC = _load_swing_config()
_BT = _load_swing_backtest_config()

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_ACCUM_JOURNAL_PATH = Path(APP_CFG.storage.accum_journal)
DEFAULT_TRADE_JOURNAL_PATH = Path(APP_CFG.storage.trade_journal)

FOREIGN_BOUNCE_SETUP = "foreign-bounce"
_DEFAULT_SETUP_TARGET = _SC.setup_targets.get("default")
FOREIGN_BOUNCE_TAKE_PROFIT = (
    _DEFAULT_SETUP_TARGET.take_profit_pct
    if _DEFAULT_SETUP_TARGET else Decimal(str(_BT.take_profit_pct))
)
FOREIGN_BOUNCE_STOP_LOSS = (
    _DEFAULT_SETUP_TARGET.stop_loss_pct
    if _DEFAULT_SETUP_TARGET else Decimal(str(_BT.stop_loss_pct))
)


def _setup_config() -> SwingSetupCatalogConfig:
    return build_swing_setup_catalog_config(_SC)


def _accumulation_log_impl(
    ticker: str,
    window: int,
    entry_price: Optional[float],
    from_analysis: bool,
    setup: str,
    with_regime: bool,
    regime_universe: Optional[str],
    benchmark: str,
    journal_path: Path,
    db_path: Path,
) -> None:
    """Thin adapter wrapper: wires repos → calls LogSwingCandidateUseCase → formats output."""
    from src.application.services.accumulation_journal import AccumulationJournalService
    from src.application.use_case.log_swing_candidate_use_case import (
        LogSwingCandidateRequest,
        LogSwingCandidateUseCase,
    )
    from src.infrastructure.persistence.accumulation_journal_csv_writer import (
        AccumulationJournalCsvWriter,
    )
    from src.infrastructure.persistence.trade_journal_jsonl_writer import TradeJournalJsonlWriter

    ticker_upper = ticker.upper()
    logged_at = date.today()
    setup_name = setup.lower()
    if from_analysis and setup_name not in AVAILABLE_SWING_SETUPS:
        typer.echo(
            f"Unknown swing setup '{setup}'. Available setups: {', '.join(AVAILABLE_SWING_SETUPS)}",
            err=True,
        )
        raise typer.Exit(1)

    broker_repo = SQLiteBrokerRepository(db_path)
    market_repo = SQLiteMarketRepository(db_path=db_path)
    _sb = create_readonly_stockbit_providers(db_path)
    screen_uc = create_accumulation_screen_use_case(
        broker_repository=broker_repo,
        market_repository=market_repo,
        stockbit_providers=_sb,
        ticker_profile_classifier_factory=create_ticker_profile_classifier,
    )
    journal_svc = AccumulationJournalService(
        store=AccumulationJournalCsvWriter(journal_path),
        repository=market_repo,
    )
    regime_uc = None
    regime_tickers: list[str] = []
    if with_regime:
        try:
            regime_uc = create_market_context_engine(
                db_path=db_path,
                universe=regime_universe or APP_CFG.analysis.regime_universe,
                benchmark=benchmark,
            )
        except Exception as exc:
            typer.echo(f"Warning: could not resolve regime universe: {exc}", err=True)

    log_uc = LogSwingCandidateUseCase(
        screen_use_case=screen_uc,
        journal_service=journal_svc,
        market_repository=market_repo,
        trade_journal_store=TradeJournalJsonlWriter(journal_path.parent / "trades.jsonl"),
        regime_use_case=regime_uc,
    )
    result = log_uc.execute(LogSwingCandidateRequest(
        ticker=ticker_upper,
        window_days=window,
        entry_price=Decimal(str(entry_price)) if entry_price is not None else None,
        from_analysis=from_analysis,
        setup=setup_name if from_analysis else None,
        with_regime=with_regime,
        regime_universe=regime_tickers,
        benchmark_ticker=benchmark,
        logged_at=logged_at,
        tier1_broker_codes=_SC.tier1_broker_codes,
        sector_breadth_enabled=_SC.sector_breadth_enabled,
        sector_breadth_threshold=_SC.sector_breadth_threshold,
        sector_breadth_bonus_pts=_SC.sector_breadth_bonus_pts,
        sector_breadth_min_tickers=_SC.sector_breadth_min_tickers,
        setup_config=_setup_config(),
        resistance_gate_enabled=_SC.resistance_gate_enabled,
        resistance_headroom_min_pct=_SC.resistance_headroom_min_pct,
        ex_date_warning_days=_SC.ex_date_warning_days,
        take_profit_pct=FOREIGN_BOUNCE_TAKE_PROFIT,
        stop_loss_pct=FOREIGN_BOUNCE_STOP_LOSS,
        max_hold_days=_BT.max_hold_days,
    ))

    if result.candidate_foreign_flow_score is None and entry_price is None:
        typer.echo(
            f"Warning: no accumulation data for {ticker_upper} in "
            f"the last {window} broker sessions. "
            "Logging without a foreign-flow score.",
            err=True,
        )

    if not result.written:
        typer.echo(
            f"Already logged {ticker_upper} for {logged_at} (window={window} sessions) — "
            f"no new row added ({journal_path})"
        )
        return

    score_str = (
        f"{result.candidate_foreign_flow_score:.1f}"
        if result.candidate_foreign_flow_score is not None
        else "N/A"
    )
    pattern_str = f" | pattern: {result.pattern}" if result.pattern else ""
    decision_str = (
        f" | setup={setup_name} | match={result.setup_match}"
        if from_analysis else ""
    )
    plan_str = (
        f" | plan entry={result.entry_price:,.0f} stop={result.planned_stop:,.0f} "
        f"target={result.planned_target:,.0f} hold={_BT.max_hold_days}d"
        if from_analysis and result.planned_stop is not None and result.planned_target is not None
        else ""
    )
    regime_str = f" | regime={result.regime}" if result.regime else ""
    typer.echo(
        f"Logged {ticker_upper} | {logged_at} | window={window} sessions | "
        f"score={score_str}{pattern_str}{decision_str}{regime_str}{plan_str} → {journal_path}"
    )
    if from_analysis and result.failed_gates:
        typer.echo("Failed gates:")
        for gate in result.failed_gates:
            typer.echo(f"  - {gate}")


def accumulation_log(
    ticker: Annotated[
        str,
        typer.Option("--ticker", "-t", help="Ticker symbol to log (e.g. BBRI)"),
    ],
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation window in broker sessions", min=3),
    ] = 7,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry-price", help="Entry price override (default = latest close)"),
    ] = None,
    from_analysis: Annotated[
        bool,
        typer.Option(
            "--from-analysis",
            help="Record setup match, failed gates, and trade plan fields",
        ),
    ] = False,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to journal with --from-analysis"),
    ] = FOREIGN_BOUNCE_SETUP,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Include market regime label in journal row"),
    ] = False,
    regime_universe: Annotated[
        Optional[str],
        typer.Option("--regime-universe", help="Universe for regime breadth"),
    ] = "lq45",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "IHSG",
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Journal CSV path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Log an accumulation candidate to the trade journal.

    Runs the accumulation screen for TICKER and appends one row to the
    journal CSV. Idempotent: re-running for the same (date, ticker, window)
    never duplicates rows.

    Example:
        saham trade log swing --ticker BBRI --window 7
        saham trade log swing --ticker BBCA --entry-price 9450
        saham trade log swing --ticker BBRI --from-analysis --with-regime
    """
    _accumulation_log_impl(
        ticker=ticker,
        window=window,
        entry_price=entry_price,
        from_analysis=from_analysis,
        setup=setup,
        with_regime=with_regime,
        regime_universe=regime_universe,
        benchmark=benchmark,
        journal_path=journal or DEFAULT_ACCUM_JOURNAL_PATH,
        db_path=db_path or DEFAULT_DB_PATH,
    )


def accumulation_review(
    horizon: Annotated[
        int,
        typer.Option("--horizon", help="Trading days forward for max/min window", min=1),
    ] = 10,
    min_foreign_flow_score: Annotated[
        float,
        typer.Option(
            "--min-foreign-flow-score",
            help="Only include entries with foreign-flow score >= this",
        ),
    ] = 0.0,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Journal CSV path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Review accumulation trade journal: forward returns by foreign-flow score and pattern.

    Fetches actual forward closes from the local database and computes
    what the foreign-flow score thresholds actually delivered.

    Example:
        saham trade review swing
        saham trade review swing --horizon 10 --min-foreign-flow-score 70
    """
    from src.application.services.accumulation_journal import AccumulationJournalService
    from src.infrastructure.persistence.accumulation_journal_csv_writer import (
        AccumulationJournalCsvWriter,
    )

    journal_path = journal or DEFAULT_ACCUM_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    if not journal_path.exists():
        typer.echo(
            f"No journal found at '{journal_path}'.\n"
            "Run `saham trade log swing --ticker BBRI` first.",
            err=True,
        )
        raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    store = AccumulationJournalCsvWriter(journal_path)
    service = AccumulationJournalService(store=store, repository=market_repo)

    typer.echo(f"Reviewing journal ({journal_path}) | horizon={horizon}d ...")
    report = service.review(horizon_days=horizon)

    from src.adapters.cli.trade_accum_display import display_journal_review

    display_journal_review(
        report=report,
        journal_path=journal_path,
        horizon=horizon,
        min_foreign_flow_score=min_foreign_flow_score,
    )
