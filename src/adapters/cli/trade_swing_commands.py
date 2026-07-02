"""
CLI implementation functions for saham trade swing commands.

Public command registration lives in lifecycle routers:
  saham trade size
  saham trade backtest-swing

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_swing_display import display_swing_backtest
from src.application.services.bootstrap import create_indicator_registry, create_risk_engine
from src.application.services.position_sizer import compute_position_size
from src.application.services.swing_backtest_attribution import AttributionBucketPolicy
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.services.swing_tuning_contracts import (
    build_tuning_config_diff_draft,
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
)
from src.application.services.swing_tuning_review_journal import (
    SwingTuningReviewJournal,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    SwingSetupCatalogConfig,
)
from src.application.use_case.swing_backtest_use_case import (
    FOREIGN_BOUNCE_SETUP as BACKTEST_FOREIGN_BOUNCE_SETUP,
)
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestUseCase,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.swing_backtest_config import (
    load_swing_backtest_config as _load_swing_backtest_config,
)
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_config
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_SWING_TUNING_REVIEW_JOURNAL_PATH = Path(
    APP_CFG.storage.swing_tuning_review_journal
)
_SC = _load_swing_config()
_BT = _load_swing_backtest_config()
_ASC = load_accumulation_screener_config()


def _setup_config() -> SwingSetupCatalogConfig:
    return build_swing_setup_catalog_config(_SC)


def _parse_regime_filter(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    regimes = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    valid = {"RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE"}
    invalid = [regime for regime in regimes if regime not in valid]
    if invalid:
        raise typer.BadParameter(
            "--allow-regimes must contain only: RISK_ON, NEUTRAL, RISK_OFF, VOLATILE"
        )
    return regimes


def _run_swing_backtest(
    *,
    tickers: list[str] | None,
    universe: str | None,
    setup: str,
    start: str,
    end: str | None,
    capital: int,
    risk_pct: float,
    max_positions: int,
    take_profit: float,
    stop_loss: float,
    max_hold: int,
    cost_bps: float,
    with_regime: bool,
    allow_regimes: str | None,
    benchmark: str,
    db_path: Path | None,
    announce: bool,
) -> SwingBacktestResponse:
    setup_name = setup.lower()
    if setup_name not in AVAILABLE_SWING_SETUPS:
        typer.echo(
            f"Unknown swing setup '{setup}'. "
            f"Available setups: {', '.join(AVAILABLE_SWING_SETUPS)}",
            err=True,
        )
        raise typer.Exit(1)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to backtest. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        allowed_regimes = _parse_regime_filter(allow_regimes)
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if announce:
        typer.echo(
            f"Backtesting {len(ticker_list)} tickers | {start_date} to {end_date} | "
            f"setup={setup_name} | max positions={max_positions}..."
        )

    use_case = SwingBacktestUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
        derived_feature_policy=_ASC.derived_features,
        risk_engine=create_risk_engine(resolved_db, with_enrichment=True),
    )
    try:
        return use_case.execute(SwingBacktestRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            setup=setup_name,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            max_positions=max_positions,
            take_profit_pct=Decimal(str(take_profit)),
            stop_loss_pct=Decimal(str(stop_loss)),
            max_hold_days=max_hold,
            cost_bps=Decimal(str(cost_bps)),
            include_regime=with_regime or bool(allowed_regimes),
            benchmark_ticker=benchmark,
            allowed_regimes=allowed_regimes,
            setup_targets=_SC.setup_targets,
            setup_config=_setup_config(),
            resistance_gate_enabled=_SC.resistance_gate_enabled,
            resistance_headroom_min_pct=_SC.resistance_headroom_min_pct,
            ex_date_warning_days=_SC.ex_date_warning_days,
            forward_data_lookahead_days=_BT.forward_data_lookahead_days,
            same_day_exit_priority=_BT.same_day_exit_priority,
            attribution_bucket_policy=AttributionBucketPolicy(
                high_min_score=_BT.attribution_high_min_score,
                mid_min_score=_BT.attribution_mid_min_score,
            ),
        ))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


def _swing_backtest_payload(response: SwingBacktestResponse) -> dict:
    return {
        "schema_version": 1,
        "artifact_type": "swing_backtest",
        "setup": response.setup,
        "start_date": response.start_date.isoformat(),
        "end_date": response.end_date.isoformat(),
        "initial_capital": str(response.initial_capital),
        "cost_bps": str(response.cost_bps),
        "final_equity": str(response.final_equity),
        "total_return_pct": response.total_return_pct,
        "max_drawdown_pct": response.max_drawdown_pct,
        "trade_count": response.trade_count,
        "win_rate_pct": response.win_rate_pct,
        "avg_trade_return_pct": response.avg_trade_return_pct,
        "profit_factor": response.profit_factor,
        "exposure_pct": response.exposure_pct,
        "skipped_no_cash": response.skipped_no_cash,
        "skipped_duplicate": response.skipped_duplicate,
        "skipped_no_forward_data": response.skipped_no_forward_data,
        "skipped_by_regime": response.skipped_by_regime,
        "warnings": response.warnings,
        "regime_stats": [stat.to_dict() for stat in response.regime_stats],
        "regime_by_date": {
            key.isoformat(): value.to_dict()
            for key, value in response.regime_by_date.items()
        },
        "attribution_summary": response.attribution_summary.to_dict(),
        "trades": [trade.to_dict() for trade in response.trades],
        "candidate_observations": [
            observation.to_dict()
            for observation in response.candidate_observations
        ],
        "equity_curve": [point.to_dict() for point in response.equity_curve],
    }


def _swing_tuning_payload(response: SwingBacktestResponse) -> dict:
    plan = build_tuning_readiness_plan(response.attribution_summary)
    proposal = build_tuning_proposal_draft(response.attribution_summary)
    config_diff = build_tuning_config_diff_draft(response.attribution_summary)
    return {
        "schema_version": 1,
        "artifact_type": "swing_tuning_review",
        "intent": "deterministic_backtest_attribution_to_config_review_no_apply",
        "setup": response.setup,
        "start_date": response.start_date.isoformat(),
        "end_date": response.end_date.isoformat(),
        "sample": response.attribution_summary.sample_quality.to_dict(),
        "backtest_summary": {
            "initial_capital": str(response.initial_capital),
            "final_equity": str(response.final_equity),
            "total_return_pct": response.total_return_pct,
            "max_drawdown_pct": response.max_drawdown_pct,
            "trade_count": response.trade_count,
            "win_rate_pct": response.win_rate_pct,
            "avg_trade_return_pct": response.avg_trade_return_pct,
            "profit_factor": response.profit_factor,
            "candidate_observation_count": len(response.candidate_observations),
        },
        "attribution_summary": response.attribution_summary.to_dict(),
        "tuning_plan": plan.to_dict(),
        "tuning_proposal": proposal.to_dict(),
        "tuning_config_diff": config_diff.to_dict(),
        "apply": {
            "supported": False,
            "reason": "This command is review-only. Edit YAML manually after human review.",
        },
    }


def _swing_tuning_patch_payload(review_payload: dict) -> dict:
    tuning_config_diff = review_payload.get("tuning_config_diff") or {}
    diff_items = tuning_config_diff.get("diff_items") or []
    patch_items = [
        {
            "target_path": item.get("target_path"),
            "parsed_target_path": item.get("parsed_target_path"),
            "current_value": item.get("current_value"),
            "proposed_value": item.get("proposed_value"),
            "rationale": item.get("rationale"),
            "confidence": item.get("confidence"),
            "status": item.get("status"),
            "value_selection_policy": item.get("value_selection_policy"),
            "target_classification": item.get("target_classification"),
            "evidence_snapshot": item.get("evidence_snapshot"),
            "evidence_dimensions": item.get("evidence_dimensions"),
        }
        for item in diff_items
        if item.get("proposed_value") is not None
    ]
    return {
        "schema_version": 1,
        "artifact_type": "swing_tuning_patch_review",
        "intent": "review_only_candidate_config_patch_no_apply",
        "source_review": {
            "setup": review_payload.get("setup"),
            "start_date": review_payload.get("start_date"),
            "end_date": review_payload.get("end_date"),
            "sample": review_payload.get("sample"),
            "backtest_summary": review_payload.get("backtest_summary"),
            "tuning_config_diff_status": tuning_config_diff.get("status"),
            "tuning_config_diff_summary": tuning_config_diff.get("summary"),
        },
        "patch_items": patch_items,
        "item_count": len(patch_items),
        "apply": {
            "supported": False,
            "reason": "Patch export is review-only and must not mutate YAML.",
        },
    }


def _export_swing_tuning_patch(review_payload: dict, path: Path) -> dict:
    patch_payload = _swing_tuning_patch_payload(review_payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(patch_payload, indent=2, default=str) + "\n")
    return {
        "path": str(path),
        "item_count": patch_payload["item_count"],
        "artifact_type": patch_payload["artifact_type"],
    }


# ─── swing backtest command ──────────────────────────────────────────────────

def swing_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_SETUP,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = APP_CFG.backtest.start_date,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = _BT.capital,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = _BT.risk_pct,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = _BT.max_positions,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = _BT.take_profit_pct,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = _BT.stop_loss_pct,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = _BT.max_hold_days,
    cost_bps: Annotated[
        float,
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = _BT.cost_bps,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Group trades by entry-date market regime"),
    ] = False,
    allow_regimes: Annotated[
        Optional[str],
        typer.Option(
            "--allow-regimes",
            help="Comma-separated entry regimes allowed to open trades",
        ),
    ] = None,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = APP_CFG.analysis.benchmark,
    show_trades: Annotated[
        int,
        typer.Option("--show-trades", help="Number of recent trades to print", min=0),
    ] = 20,
    with_attribution: Annotated[
        bool,
        typer.Option(
            "--with-attribution",
            help="Show deterministic grouped attribution summary for tuning",
        ),
    ] = False,
    with_tuning_plan: Annotated[
        bool,
        typer.Option(
            "--with-tuning-plan",
            help="Show deterministic tuning readiness plan; no AI or YAML changes",
        ),
    ] = False,
    with_tuning_proposal: Annotated[
        bool,
        typer.Option(
            "--with-tuning-proposal",
            help="Show deterministic dry-run tuning proposal targets; no YAML diff",
        ),
    ] = False,
    with_tuning_diff: Annotated[
        bool,
        typer.Option(
            "--with-tuning-diff",
            help=(
                "Show guarded dry-run tuning config diff with current/proposed "
                "values; no apply"
            ),
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Walk-forward backtest for the deterministic swing workflow.

    This validates the full daily process: scan, apply setup gates, rank
    candidates, open only within portfolio limits, avoid duplicate positions,
    and exit by TP/SL/max-hold. It reads local cached market and broker data.
    """
    response = _run_swing_backtest(
        tickers=tickers,
        universe=universe,
        setup=setup,
        start=start,
        end=end,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        take_profit=take_profit,
        stop_loss=stop_loss,
        max_hold=max_hold,
        cost_bps=cost_bps,
        with_regime=with_regime,
        allow_regimes=allow_regimes,
        benchmark=benchmark,
        db_path=db_path,
        announce=output_format != "json",
    )

    if output_format == "json":
        payload = _swing_backtest_payload(response)
        if with_tuning_plan:
            payload["tuning_plan"] = build_tuning_readiness_plan(
                response.attribution_summary
            ).to_dict()
        if with_tuning_proposal:
            payload["tuning_proposal"] = build_tuning_proposal_draft(
                response.attribution_summary
            ).to_dict()
        if with_tuning_diff:
            payload["tuning_config_diff"] = build_tuning_config_diff_draft(
                response.attribution_summary
            ).to_dict()
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    display_swing_backtest(
        response,
        show_trades=show_trades,
        show_attribution=with_attribution,
        show_tuning_plan=with_tuning_plan,
        show_tuning_proposal=with_tuning_proposal,
        show_tuning_diff=with_tuning_diff,
    )


def swing_tune(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_SETUP,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = APP_CFG.backtest.start_date,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = _BT.capital,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = _BT.risk_pct,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = _BT.max_positions,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = _BT.take_profit_pct,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = _BT.stop_loss_pct,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = _BT.max_hold_days,
    cost_bps: Annotated[
        float,
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = _BT.cost_bps,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Group evidence by entry-date market regime"),
    ] = False,
    allow_regimes: Annotated[
        Optional[str],
        typer.Option(
            "--allow-regimes",
            help="Comma-separated entry regimes allowed to open trades",
        ),
    ] = None,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = APP_CFG.analysis.benchmark,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    save: Annotated[
        bool,
        typer.Option(
            "--save",
            help="Append the tuning review artifact to the local JSONL journal",
        ),
    ] = False,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Override swing tuning review journal path"),
    ] = None,
    export_patch: Annotated[
        Optional[Path],
        typer.Option(
            "--export-patch",
            help="Write proposed config values to a review-only JSON patch artifact",
        ),
    ] = None,
) -> None:
    """
    Build deterministic swing tuning review from walk-forward attribution.

    This is the first-class tuning-loop entry point for swing. It replays the
    deterministic workflow, summarizes attribution, and emits guarded config
    review artifacts. It never calls AI and never writes YAML.
    """
    response = _run_swing_backtest(
        tickers=tickers,
        universe=universe,
        setup=setup,
        start=start,
        end=end,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        take_profit=take_profit,
        stop_loss=stop_loss,
        max_hold=max_hold,
        cost_bps=cost_bps,
        with_regime=with_regime,
        allow_regimes=allow_regimes,
        benchmark=benchmark,
        db_path=db_path,
        announce=output_format != "json",
    )

    payload = _swing_tuning_payload(response)
    if save:
        journal_path = journal or DEFAULT_SWING_TUNING_REVIEW_JOURNAL_PATH
        save_result = SwingTuningReviewJournal(
            SwingTuningReviewJsonlWriter(journal_path)
        ).append_review(payload)
        payload["persistence"] = {
            **save_result.to_dict(),
            "path": str(journal_path),
        }
    if export_patch is not None:
        payload["patch_export"] = _export_swing_tuning_patch(
            payload,
            export_patch,
        )

    if output_format == "json":
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    display_swing_backtest(
        response,
        show_trades=0,
        show_attribution=True,
        show_tuning_plan=True,
        show_tuning_proposal=True,
        show_tuning_diff=True,
    )
    if save:
        persistence = payload["persistence"]
        typer.echo(
            f"Saved swing tuning review -> {persistence['path']} "
            f"(records={persistence['record_count']})"
        )
    if export_patch is not None:
        patch_export = payload["patch_export"]
        typer.echo(
            f"Exported swing tuning patch -> {patch_export['path']} "
            f"(items={patch_export['item_count']})"
        )


# ─── size command ─────────────────────────────────────────────────────────────

def size(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBRI)")],
    capital: Annotated[
        Optional[int],
        typer.Option(
            "--capital",
            "-c",
            help="Total capital in IDR (default: from config/user.yaml)",
            min=1,
        ),
    ] = None,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade"),
    ] = APP_CFG.swing.risk_pct,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance"),
    ] = APP_CFG.swing.atr_mult,
    rr: Annotated[
        float,
        typer.Option("--rr", help="Reward:risk ratio for target"),
    ] = APP_CFG.swing.rr,
    atr_period: Annotated[
        int,
        typer.Option("--atr-period", help="ATR period (default: 14)", min=2),
    ] = 14,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    ATR-based position sizing calculator for IDX swing trades.

    Computes stop price (ATR × multiplier, default 1.5) below entry, target
    at reward:risk ratio (default 2×), and exact lot count from fixed-fractional
    capital risk.

    Examples:
        saham trade size BBRI --capital 10000000
        saham trade size BBRI --capital 10000000 --risk-pct 2 --entry 4825
        saham trade size BBRI --capital 50000000 --risk-pct 1 --rr 2.5
        saham trade size BBRI --capital 10000000 --atr-mult 2.0
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_upper = ticker.upper()
    today = date.today()

    if capital is None:
        _cfg = get_swing_default("capital")
        if _cfg is not None:
            capital = int(_cfg)
    if capital is None:
        typer.echo(
            "Error: --capital is required. Pass it as a flag or set "
            "swing.capital in config/user.yaml.",
            err=True,
        )
        raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    registry = create_indicator_registry()

    candles = market_repo.get_candles(ticker_upper)
    if not candles:
        typer.echo(
            f"No data for {ticker_upper}. Run: saham fetch market {ticker_upper} --days 365",
            err=True,
        )
        raise typer.Exit(1)

    latest_close = candles[-1].close

    # Compute ATR
    atr_value: Decimal | None = None
    try:
        atr_values = registry.compute("ATR", candles, atr_period)
        if atr_values:
            atr_value = atr_values[-1][1]  # registry returns (date, value) tuples
    except Exception as e:
        typer.echo(f"Error computing ATR: {e}", err=True)
        raise typer.Exit(1)

    if not atr_value or atr_value <= 0:
        typer.echo(
            f"Cannot compute ATR({atr_period}) for {ticker_upper} — insufficient data.", err=True
        )
        typer.echo(f"Tip: Run: saham fetch market {ticker_upper} --days 90", err=True)
        raise typer.Exit(1)

    entry_dec = Decimal(str(entry_price)) if entry_price else latest_close

    try:
        result = compute_position_size(
            entry=entry_dec,
            atr=atr_value,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            atr_multiplier=Decimal(str(atr_mult)),
            reward_risk=Decimal(str(rr)),
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        out = {
            "ticker": ticker_upper,
            "date": str(today),
            "entry": float(result.entry_price),
            "atr": float(result.atr),
            "atr_period": atr_period,
            "atr_multiplier": float(result.atr_multiplier),
            "stop_price": float(result.stop_price),
            "stop_distance": float(result.stop_distance),
            "stop_pct": float(result.stop_pct),
            "target_price": float(result.target_price),
            "target_pct": float(result.target_pct),
            "reward_risk_ratio": float(result.reward_risk_ratio),
            "capital": float(result.capital),
            "risk_pct": risk_pct,
            "risk_amount": float(result.risk_amount),
            "reward_amount": float(result.reward_amount),
            "lots": result.lots,
            "shares": result.shares,
            "position_cost": float(result.position_cost),
            "capital_used_pct": float(result.capital_used_pct),
        }
        typer.echo(json.dumps(out, indent=2))
        return

    from src.adapters.cli.trade_swing_size_display import display_position_size

    display_position_size(
        ticker=ticker_upper,
        today=today,
        capital=capital,
        risk_pct=risk_pct,
        entry_price=entry_price,
        entry_dec=entry_dec,
        atr_value=atr_value,
        atr_period=atr_period,
        result=result,
    )
