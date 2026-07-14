"""
Risk engine construction (infrastructure composition root).

Wires a fully-configured RiskEngine: loads risk-related config via the shared
application-layer config resolvers, builds the indicator registry, and
injects SQLite-backed repositories and Stockbit-backed enrichment providers.
This is concrete wiring, so it lives in infrastructure, not application.

Layer: Infrastructure (composition root)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.application.services.engine_bootstrap.risk_config_resolvers import (
    _resolve_indicator_evaluator_config,
    _resolve_market_context_gate,
    _resolve_risk_indicator_defaults,
    _resolve_technical_gate_config,
    resolve_risk_gates,
)
from src.application.services.indicator_evaluator import IndicatorEvaluator
from src.application.services.risk_engine import RiskEngine
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
    StockbitSQLiteConnectionProvider,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

if TYPE_CHECKING:
    from src.application.ports.rules_loader import RulesLoader


def create_risk_engine(
    db_path: "str | Path",
    with_enrichment: bool = False,
    rules_loader: "RulesLoader | None" = None,
    config: dict | None = None,
) -> "RiskEngine":
    """
    Create a fully-configured RiskEngine with all three gates wired.

    Args:
        db_path: Path to the SQLite database (e.g. data/db/data.db).
        with_enrichment: When True, inject FundamentalsProvider and
            BandarDetectorProvider so FundamentalGate and BandarGate
            can fire from the engine's own assess() call.
            When False (default), LiquidityGate still fires from candle
            data; the other gates skip gracefully.
        rules_loader: RulesLoader port injected by the caller's adapter.
            Required only when the caller sends requests with rules_file set
            (custom-rules mode) via engine.assess_request().
        config: Loaded configuration dict.
    """
    resolved = Path(db_path)
    repository = SQLiteMarketRepository(db_path=resolved)
    broker_repository = SQLiteBrokerRepository(db_path=resolved)
    registry = create_indicator_registry(
        market_repository=repository,
        broker_repository=broker_repository,
    )

    cfg = config if config is not None else {}
    structural_gates, execution_gates = resolve_risk_gates(cfg)
    indicator_defaults = _resolve_risk_indicator_defaults(cfg)
    market_context_gate = _resolve_market_context_gate(cfg)
    indicator_evaluator_config = _resolve_indicator_evaluator_config(cfg)
    technical_gate_config = _resolve_technical_gate_config(cfg)

    fund_prov = None
    bandar_prov = None
    shareholding_prov = None
    if with_enrichment:
        connection_provider = StockbitSQLiteConnectionProvider()
        stockbit_config = load_stockbit_provider_config()
        fund_prov = StockbitFundamentalsProvider(
            api_client=None,
            db_path=resolved,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        )
        bandar_prov = StockbitBandarDetectorProvider(
            api_client=None,
            db_path=resolved,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        )
        shareholding_prov = StockbitShareholdingProvider(
            api_client=None,
            db_path=resolved,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        )

    return RiskEngine(
        repository=repository,
        registry=registry,
        structural_gates=structural_gates,
        execution_gates=execution_gates,
        fundamentals_provider=fund_prov,
        bandar_provider=bandar_prov,
        shareholding_provider=shareholding_prov,
        indicator_evaluator=IndicatorEvaluator(indicator_evaluator_config),
        indicator_defaults=indicator_defaults,
        market_context_gate=market_context_gate,
        technical_gate_config=technical_gate_config,
        rules_loader=rules_loader,
    )
