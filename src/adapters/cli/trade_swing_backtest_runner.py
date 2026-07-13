"""
Shared runner helper for swing backtesting and tuning.

Layer: Adapter
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import typer

from src.adapters.cli.risk_engine_helper import create_configured_risk_engine
from src.application.services.swing_backtest_attribution import AttributionBucketPolicy
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    SwingSetupCatalogConfig,
)
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestUseCase,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
    load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.config_backed_market_context_provider import (
    ConfigBackedMarketContextProvider,
)
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.config.swing_backtest_config import (
    SwingBacktestConfig,
)
from src.infrastructure.config.swing_backtest_config import (
    load_swing_backtest_config as _load_swing_backtest_config,
)
from src.infrastructure.config.swing_config import SwingConfig
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)


@dataclass(frozen=True)
class SwingBacktestRunnerConfig:
    swing_config: SwingConfig
    backtest_config: SwingBacktestConfig
    accumulation_config: AccumulationScreenerConfig
    setup_config: SwingSetupCatalogConfig


def load_swing_backtest_runner_config() -> SwingBacktestRunnerConfig:
    swing_config = _load_swing_config()
    return SwingBacktestRunnerConfig(
        swing_config=swing_config,
        backtest_config=_load_swing_backtest_config(),
        accumulation_config=load_accumulation_screener_config(),
        setup_config=build_swing_setup_catalog_config(swing_config),
    )


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
    config: SwingBacktestRunnerConfig | None = None,
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
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(resolved_db),
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

    runner_config = config or load_swing_backtest_runner_config()

    broker_repo = SQLiteBrokerRepository(resolved_db)
    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    use_case = SwingBacktestUseCase(
        broker_repository=broker_repo,
        market_repository=market_repo,
        indicator_registry=create_indicator_registry(),
        rules_loader=RulesYamlLoader(),
        derived_feature_policy=runner_config.accumulation_config.derived_features,
        risk_engine=create_configured_risk_engine(resolved_db, with_enrichment=True),
        market_context_provider=ConfigBackedMarketContextProvider(
            market_repository=market_repo,
            broker_repository=broker_repo,
        ),
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
            setup_targets=runner_config.swing_config.setup_targets,
            setup_config=runner_config.setup_config,
            resistance_gate_enabled=runner_config.swing_config.resistance_gate_enabled,
            resistance_headroom_min_pct=runner_config.swing_config.resistance_headroom_min_pct,
            ex_date_warning_days=runner_config.swing_config.ex_date_warning_days,
            forward_data_lookahead_days=runner_config.backtest_config.forward_data_lookahead_days,
            same_day_exit_priority=runner_config.backtest_config.same_day_exit_priority,
            attribution_bucket_policy=AttributionBucketPolicy(
                high_min_score=runner_config.backtest_config.attribution_high_min_score,
                mid_min_score=runner_config.backtest_config.attribution_mid_min_score,
            ),
        ))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
