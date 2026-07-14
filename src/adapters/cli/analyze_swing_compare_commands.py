"""
CLI implementation for `saham analyze swing-compare`.

Compares swing backtest regime variants side-by-side. Uses the same
portfolio simulation as `saham trade backtest-swing`; only the allowed
entry regimes differ per variant.

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.analyze_swing_command_config import (
    load_analyze_swing_command_config,
)
from src.adapters.cli.analyze_swing_display import display_swing_compare
from src.adapters.cli.risk_engine_helper import create_configured_risk_engine
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.evaluate_swing_setup_use_case import AVAILABLE_SWING_SETUPS
from src.application.use_case.swing_backtest_use_case import (
    FOREIGN_BOUNCE_SETUP as BACKTEST_FOREIGN_BOUNCE_SETUP,
)
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestUseCase,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.config_backed_market_context_provider import (
    ConfigBackedMarketContextProvider,
)
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

SWING_COMPARE_VARIANTS: dict[str, tuple[str, ...]] = {
    "baseline": (),
    "sideways_only": ("NEUTRAL", "RISK_ON"),
    "weak_plus": ("VOLATILE", "NEUTRAL", "RISK_ON"),
}


def _parse_compare_variants(value: str) -> tuple[str, ...]:
    variants = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not variants:
        raise typer.BadParameter("--variants must contain at least one variant")
    invalid = [variant for variant in variants if variant not in SWING_COMPARE_VARIANTS]
    if invalid:
        available = ", ".join(SWING_COMPARE_VARIANTS)
        raise typer.BadParameter(
            f"Unknown variants: {', '.join(invalid)}. Available: {available}"
        )
    return variants


def swing_compare(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`"
        ),
    ] = None,
    variants: Annotated[
        str,
        typer.Option(
            "--variants",
            help="Comma-separated variants: baseline, sideways_only, weak_plus",
        ),
    ] = "baseline,sideways_only,weak_plus",
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_SETUP,
    start: Annotated[
        Optional[str],
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = None,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = None,
    risk_pct: Annotated[
        Optional[float],
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = None,
    max_positions: Annotated[
        Optional[int],
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = None,
    take_profit: Annotated[
        Optional[float],
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = None,
    stop_loss: Annotated[
        Optional[float],
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = None,
    max_hold: Annotated[
        Optional[int],
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = None,
    cost_bps: Annotated[
        Optional[float],
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = None,
    benchmark: Annotated[
        Optional[str],
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = None,
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Compare swing backtest regime variants side-by-side.

    Variants use the same portfolio simulation as `saham trade backtest-swing`;
    only the allowed entry regimes differ.
    """
    app_cfg = load_app_config()
    start = start or app_cfg.backtest.start_date
    benchmark = benchmark or app_cfg.analysis.benchmark
    output_format = output_format or app_cfg.analysis.format

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
        variant_names = _parse_compare_variants(variants)
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or Path(app_cfg.storage.db_path)
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(resolved_db),
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to compare. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    if output_format != "json":
        typer.echo(
            f"Comparing {len(variant_names)} variants over {len(ticker_list)} tickers | "
            f"{start_date} to {end_date}..."
        )

    cfg = load_analyze_swing_command_config()

    resolved_capital = (
        capital if capital is not None else cfg.swing_backtest_config.capital
    )
    resolved_risk_pct = (
        risk_pct if risk_pct is not None else cfg.swing_backtest_config.risk_pct
    )
    resolved_max_positions = (
        max_positions if max_positions is not None
        else cfg.swing_backtest_config.max_positions
    )
    resolved_take_profit = (
        take_profit if take_profit is not None
        else cfg.swing_backtest_config.take_profit_pct
    )
    resolved_stop_loss = (
        stop_loss if stop_loss is not None
        else cfg.swing_backtest_config.stop_loss_pct
    )
    resolved_max_hold = (
        max_hold if max_hold is not None else cfg.swing_backtest_config.max_hold_days
    )
    resolved_cost_bps = (
        cost_bps if cost_bps is not None else cfg.swing_backtest_config.cost_bps
    )

    broker_repo = SQLiteBrokerRepository(resolved_db)
    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    use_case = SwingBacktestUseCase(
        broker_repository=broker_repo,
        market_repository=market_repo,
        indicator_registry=create_indicator_registry(),
        rules_loader=RulesYamlLoader(),
        derived_feature_policy=cfg.accumulation_screener_config.derived_features,
        risk_engine=create_configured_risk_engine(resolved_db, with_enrichment=True),
        market_context_provider=ConfigBackedMarketContextProvider(
            market_repository=market_repo,
            broker_repository=broker_repo,
        ),
    )
    rows: list[tuple[str, SwingBacktestResponse]] = []
    try:
        for variant in variant_names:
            allowed_regimes = SWING_COMPARE_VARIANTS[variant]
            response = use_case.execute(SwingBacktestRequest(
                tickers=ticker_list,
                start_date=start_date,
                end_date=end_date,
                setup=setup_name,
                capital=Decimal(str(resolved_capital)),
                risk_pct=Decimal(str(resolved_risk_pct)) / Decimal("100"),
                max_positions=resolved_max_positions,
                take_profit_pct=Decimal(str(resolved_take_profit)),
                stop_loss_pct=Decimal(str(resolved_stop_loss)),
                max_hold_days=resolved_max_hold,
                cost_bps=Decimal(str(resolved_cost_bps)),
                include_regime=True,
                benchmark_ticker=benchmark,
                allowed_regimes=allowed_regimes,
                setup_config=cfg.setup_config,
                resistance_gate_enabled=cfg.swing_config.resistance_gate_enabled,
                resistance_headroom_min_pct=cfg.swing_config.resistance_headroom_min_pct,
                ex_date_warning_days=cfg.swing_config.ex_date_warning_days,
                forward_data_lookahead_days=cfg.swing_backtest_config.forward_data_lookahead_days,
                same_day_exit_priority=cfg.swing_backtest_config.same_day_exit_priority,
            ))
            rows.append((variant, response))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps({
            "schema_version": 1,
            "artifact_type": "swing_compare",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "ticker_count": len(ticker_list),
            "variants": [
                {
                    "name": name,
                    "allowed_regimes": list(SWING_COMPARE_VARIANTS[name]),
                    "cost_bps": str(response.cost_bps),
                    "total_return_pct": response.total_return_pct,
                    "max_drawdown_pct": response.max_drawdown_pct,
                    "trade_count": response.trade_count,
                    "win_rate_pct": response.win_rate_pct,
                    "profit_factor": response.profit_factor,
                    "exposure_pct": response.exposure_pct,
                    "skipped_by_regime": response.skipped_by_regime,
                }
                for name, response in rows
            ],
        }, indent=2, default=str))
        return

    display_swing_compare(
        rows=rows,
        start_date=start_date,
        end_date=end_date,
        universe_label=universe or "explicit",
        variants_by_name=SWING_COMPARE_VARIANTS,
    )
