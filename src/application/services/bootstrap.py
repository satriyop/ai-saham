"""
Application bootstrap utilities.

Provides functions for initializing application services with plugins
and persisted formulas.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from src.application.formula.parser import parse
from src.application.services.indicator_registry import IndicatorRegistry

if TYPE_CHECKING:
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.infrastructure.persistence.formula_storage import FormulaStorage
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.signal_engine import SignalEngine
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )

logger = logging.getLogger(__name__)


# ── Engine config helpers ─────────────────────────────────────────────────────

def _load_engine_config(path: Path) -> dict:
    """Load a YAML engine config file. Returns empty dict if file is absent."""
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _resolve_signal_weights(cfg: dict) -> dict[str, float] | None:
    """
    Parse enabled signal factors and return renormalized weights.

    Returns None when config is absent/empty so AssessSignalUseCase falls back
    to its built-in _DEFAULT_WEIGHTS (identical to historical behavior).
    """
    factors = cfg.get("signal_engine", {}).get("factors", {})
    active = {
        name: data["weight"]
        for name, data in factors.items()
        if data.get("enabled", True)
    }
    if not active:
        return None
    total = sum(active.values())
    return {name: w / total for name, w in active.items()}


def _resolve_signal_config(cfg: dict):
    from src.application.use_case.assess_signal_use_case import (
        ForeignFlowScoreMappingConfig,
        AnalystScoringConfig,
        BandarScoringConfig,
        ForwardPeScoringConfig,
        SeasonalityScoringConfig,
        SignalClassificationConfig,
        SignalEnrichmentConfig,
        SignalEngineConfig,
        SignalInputMappingConfig,
        SignalMissingDataConfig,
        SignalScoringConfig,
    )

    root = cfg.get("signal_engine", {})
    classification = root.get("classification", {})
    missing = root.get("missing_data", {})
    scoring = root.get("scoring", {})
    enrichment = root.get("enrichment", {})
    input_mapping = root.get("input_mapping", {})
    foreign_flow_score_mapping = input_mapping.get("foreign_flow_score", {})
    bandar = scoring.get("bandar", {})
    seasonality = scoring.get("seasonality", {})
    analyst = scoring.get("analyst", {})
    forward_pe = scoring.get("forward_pe", {})

    return SignalEngineConfig(
        classification=SignalClassificationConfig(
            strong_min_score=classification.get("strong_min_score", 70),
            moderate_min_score=classification.get("moderate_min_score", 45),
        ),
        missing_data=SignalMissingDataConfig(
            neutral_score=missing.get("neutral_score", 50.0),
            coverage_warning_missing_factors=missing.get("coverage_warning_missing_factors", 3),
        ),
        scoring=SignalScoringConfig(
            bandar=BandarScoringConfig(
                mandatory_signal_count=bandar.get("mandatory_signal_count", 3),
                signal_score_unit=bandar.get("signal_score_unit", 2),
                default_max_range=bandar.get("default_max_range", 6),
            ),
            seasonality=SeasonalityScoringConfig(
                tailwind_min_avg_return_pct=seasonality.get("tailwind_min_avg_return_pct", 0.0),
                tailwind_min_win_rate_pct=seasonality.get("tailwind_min_win_rate_pct", 50.0),
                headwind_max_avg_return_pct=seasonality.get("headwind_max_avg_return_pct", 0.0),
                headwind_max_win_rate_pct=seasonality.get("headwind_max_win_rate_pct", 50.0),
            ),
            analyst=AnalystScoringConfig(
                buy_score_max_points=analyst.get("buy_score_max_points", 60.0),
                upside_score_max_points=analyst.get("upside_score_max_points", 40.0),
                upside_cap_pct=analyst.get("upside_cap_pct", 30.0),
            ),
            forward_pe=ForwardPeScoringConfig(
                very_cheap_pe=forward_pe.get("very_cheap_pe", 10.0),
                cheap_pe=forward_pe.get("cheap_pe", 15.0),
                fair_pe=forward_pe.get("fair_pe", 20.0),
                expensive_pe=forward_pe.get("expensive_pe", 30.0),
                very_cheap_score=forward_pe.get("very_cheap_score", 95.0),
                cheap_score=forward_pe.get("cheap_score", 75.0),
                fair_score=forward_pe.get("fair_score", 50.0),
                expensive_score=forward_pe.get("expensive_score", 25.0),
                post_expensive_pe_step=forward_pe.get("post_expensive_pe_step", 10.0),
                post_expensive_score_decay=forward_pe.get("post_expensive_score_decay", 15.0),
            ),
        ),
        input_mapping=SignalInputMappingConfig(
            foreign_flow_score=ForeignFlowScoreMappingConfig(
                max_score=foreign_flow_score_mapping.get("max_score", 120.0),
                clamp=foreign_flow_score_mapping.get("clamp", True),
            ),
        ),
        enrichment=SignalEnrichmentConfig(
            insider_lookback_days=enrichment.get("insider_lookback_days", 90),
        ),
    )


def _resolve_risk_gates(cfg: dict) -> tuple[list, list]:
    """
    Parse enabled risk gates and return (structural_gates, execution_gates).

    When config is absent/empty, defaults match the previous hardcoded values.
    """
    from src.domain.rules.bandar_gate import BandarGate, BandarGateConfig
    from src.domain.rules.free_float_gate import FreeFloatGate, FreeFloatGatePolicy
    from src.domain.rules.fundamental_gate import FundamentalGate, FundamentalGatePolicy
    from src.domain.rules.liquidity_gate import LiquidityGate, LiquidityGatePolicy

    gates = cfg.get("risk_engine", {}).get("gates", {})

    structural = []
    fund = gates.get("fundamental", {})
    if fund.get("enabled", True):
        structural.append(FundamentalGate(
            distress_threshold=fund.get("piotroski_min", 3),
            policy=FundamentalGatePolicy(
                missing_data_action=fund.get("missing_data_action", "skip"),
                missing_data_confidence=fund.get("missing_data_confidence", 0),
                triggered_confidence=fund.get("triggered_confidence", 100),
                pass_confidence=fund.get("pass_confidence", 100),
            ),
        ))

    liq = gates.get("liquidity", {})
    if liq.get("enabled", True):
        structural.append(LiquidityGate(
            third_liner_cap_idr=liq.get("market_cap_floor_idr", 1_000_000_000_000),
            liquidity_floor_idr=liq.get("median_tx_floor_idr", 5_000_000_000),
            lookback_days=liq.get("lookback_days", 20),
            policy=LiquidityGatePolicy(
                missing_data_action=liq.get("missing_data_action", "skip"),
                missing_data_confidence=liq.get("missing_data_confidence", 0),
                triggered_confidence=liq.get("triggered_confidence", 100),
                pass_confidence=liq.get("pass_confidence", 100),
            ),
        ))

    ff = gates.get("free_float", {})
    if ff.get("enabled", True):
        structural.append(FreeFloatGate(
            min_free_float_pct=ff.get("min_free_float_pct", 15.0),
            policy=FreeFloatGatePolicy(
                missing_data_action=ff.get("missing_data_action", "skip"),
                missing_data_confidence=ff.get("missing_data_confidence", 0),
                triggered_confidence=ff.get("triggered_confidence", 100),
                pass_confidence=ff.get("pass_confidence", 100),
            ),
        ))

    execution = []
    bandar = gates.get("bandar", {})
    if bandar.get("enabled", True):
        execution.append(BandarGate(
            BandarGateConfig(
                distribution_labels=frozenset(bandar.get("distribution_labels", [
                    "Small Dist", "Big Dist",
                ])),
                missing_data_action=bandar.get("missing_data_action", "skip"),
                missing_data_confidence=bandar.get("missing_data_confidence", 0),
                triggered_confidence=bandar.get("triggered_confidence", 80),
                pass_confidence=bandar.get("pass_confidence", 100),
            )
        ))

    return structural, execution


def _resolve_risk_indicator_defaults(cfg: dict):
    from src.application.services.risk_engine import RiskIndicatorDefaults

    indicators = cfg.get("risk_engine", {}).get("indicators", {})
    return RiskIndicatorDefaults(
        sma_period=indicators.get("sma_period", 20),
        ema_period=indicators.get("ema_period", 20),
        rsi_period=indicators.get("rsi_period", 14),
        history_days=indicators.get("history_days", 365),
        gate_recent_candle_lookback=indicators.get("gate_recent_candle_lookback", 20),
    )


def _resolve_market_context_gate(cfg: dict):
    from src.application.services.risk_engine import MarketContextGateConfig

    gate = cfg.get("risk_engine", {}).get("market_context_gate", {})
    return MarketContextGateConfig(
        enabled=gate.get("enabled", True),
        block_when_gate_tightening=gate.get("block_when_gate_tightening", True),
        gate_is_structural=gate.get("gate_is_structural", True),
        label_prefix=gate.get("label_prefix", "regime"),
    )


def _resolve_indicator_evaluator_config(cfg: dict):
    from src.application.services.indicator_evaluator import IndicatorEvaluatorConfig

    technical = cfg.get("risk_engine", {}).get("gates", {}).get("technical", {})
    evaluator = technical.get("evaluator", {})
    return IndicatorEvaluatorConfig(
        rsi_overbought=evaluator.get("rsi_overbought", 70.0),
        rsi_oversold=evaluator.get("rsi_oversold", 30.0),
        agreement_count=evaluator.get("agreement_count", 2),
        full_agreement_confidence=evaluator.get("full_agreement_confidence", 100),
        partial_agreement_confidence=evaluator.get("partial_agreement_confidence", 50),
    )


def _resolve_technical_gate_config(cfg: dict):
    from src.domain.rules.technical_gate import TechnicalGateConfig

    technical = cfg.get("risk_engine", {}).get("gates", {}).get("technical", {})
    return TechnicalGateConfig(
        block_when_bearish=technical.get("block_when_bearish", True),
        missing_data_action=technical.get("missing_data_action", "skip"),
        missing_data_confidence=technical.get("missing_data_confidence", 0),
        pass_confidence=technical.get("pass_confidence", 100),
    )


# ── Factory functions ─────────────────────────────────────────────────────────

def create_indicator_registry(
    plugin_dir: str | None = None,
    formula_storage: "FormulaStorage | None" = None,
    load_formulas: bool = True,
    broker_repository: "BrokerDataRepository | None" = None,
    market_repository: "MarketDataRepository | None" = None,
    index_ticker: str = "IHSG",
) -> IndicatorRegistry:
    """
    Create an IndicatorRegistry with plugins and formulas loaded.

    Discovers plugins from the specified directory (or default plugins/indicators/)
    and registers them. Optionally loads persisted formulas from storage.
    Gracefully handles missing directories, invalid plugins, and invalid formulas.

    Args:
        plugin_dir: Optional path to plugin directory. None uses default.
        formula_storage: Optional FormulaStorage instance for loading formulas.
                        If None and load_formulas is True, creates default storage.
        load_formulas: Whether to load formulas from storage. Default True.

    Returns:
        IndicatorRegistry with built-in indicators, discovered plugins,
        and loaded formulas.
    """
    registry = IndicatorRegistry(
        broker_repository=broker_repository,
        market_repository=market_repository,
        index_ticker=index_ticker,
    )

    # Load plugins
    from src.infrastructure.plugins.indicator_loader import IndicatorPluginLoader

    loader = IndicatorPluginLoader(Path(plugin_dir) if plugin_dir else None)
    plugins = loader.discover()

    # Register each plugin
    for plugin_class in plugins:
        try:
            registry.register_plugin(plugin_class)
            logger.debug(f"Registered plugin: {plugin_class.name}")
        except Exception as e:
            logger.warning(f"Failed to register plugin {plugin_class.name}: {e}")

    # Load persisted formulas
    if load_formulas:
        _load_formulas_into_registry(registry, formula_storage)

    return registry


def create_risk_engine(
    db_path: "str | Path",
    with_enrichment: bool = False,
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
    """
    from pathlib import Path as _Path

    from src.application.services.risk_engine import RiskEngine
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )

    resolved = _Path(db_path)
    repository = SQLiteMarketRepository(db_path=resolved)
    broker_repository = SQLiteBrokerRepository(db_path=resolved)
    registry = create_indicator_registry(
        market_repository=repository,
        broker_repository=broker_repository,
    )

    from src.infrastructure.config.app_config import APP_CFG

    cfg = _load_engine_config(Path(APP_CFG.config_paths.risk_engine))
    structural_gates, execution_gates = _resolve_risk_gates(cfg)
    indicator_defaults = _resolve_risk_indicator_defaults(cfg)
    market_context_gate = _resolve_market_context_gate(cfg)
    indicator_evaluator_config = _resolve_indicator_evaluator_config(cfg)
    technical_gate_config = _resolve_technical_gate_config(cfg)

    fund_prov = None
    bandar_prov = None
    shareholding_prov = None
    if with_enrichment:
        from src.infrastructure.browser.stockbit_fundamentals import (
            StockbitFundamentalsProvider,
        )
        from src.infrastructure.browser.stockbit_bandar import (
            StockbitBandarDetectorProvider,
        )
        from src.infrastructure.browser.stockbit_shareholding import (
            StockbitShareholdingProvider,
        )

        fund_prov = StockbitFundamentalsProvider(broker_provider=None, db_path=resolved)
        bandar_prov = StockbitBandarDetectorProvider(broker_provider=None, db_path=resolved)
        shareholding_prov = StockbitShareholdingProvider(broker_provider=None, db_path=resolved)

    from src.application.services.indicator_evaluator import IndicatorEvaluator

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
    )


def create_signal_engine(
    db_path: "str | Path",
    with_enrichment: bool = False,
) -> "SignalEngine":
    """
    Create a fully-configured SignalEngine.

    Args:
        db_path: Path to the SQLite database (e.g. data/db/data.db).
        with_enrichment: When True, inject all 5 Stockbit enrichment providers
            (bandar, fundamentals, seasonality, analyst, forward_estimates) using
            the SQLite cache so evaluate() works without a live broker session.
            When False (default), all providers are None and all factors fall
            back to neutral (50.0) — useful for testing the engine wiring.
    """
    from pathlib import Path as _Path

    from src.application.services.signal_engine import SignalEngine

    from src.infrastructure.config.app_config import APP_CFG

    cfg = _load_engine_config(Path(APP_CFG.config_paths.signal_engine))
    weights = _resolve_signal_weights(cfg)
    signal_config = _resolve_signal_config(cfg)

    if not with_enrichment:
        return SignalEngine(weights=weights, config=signal_config)

    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )
    from src.infrastructure.persistence.sqlite_market_repository import (
        SQLiteMarketRepository,
    )

    resolved = _Path(db_path)
    market_repository = SQLiteMarketRepository(db_path=resolved)

    def _latest_close(ticker: str) -> float | None:
        candles = market_repository.get_candles(ticker)
        if not candles:
            return None
        return float(candles[-1].close)

    return SignalEngine(
        bandar_provider=StockbitBandarDetectorProvider(broker_provider=None, db_path=resolved),
        insider_activity_provider=StockbitInsiderActivityProvider(broker_provider=None, db_path=resolved),
        seasonality_provider=StockbitSeasonalityProvider(broker_provider=None, db_path=resolved),
        analyst_provider=StockbitAnalystConsensusProvider(broker_provider=None, db_path=resolved),
        forward_estimates_provider=StockbitForwardEstimatesProvider(
            broker_provider=None, db_path=resolved
        ),
        latest_price_provider=_latest_close,
        weights=weights,
        config=signal_config,
    )


def _load_formulas_into_registry(
    registry: IndicatorRegistry,
    formula_storage: "FormulaStorage | None" = None,
) -> None:
    """
    Load persisted formulas into the registry.

    Args:
        registry: IndicatorRegistry to load formulas into.
        formula_storage: Optional FormulaStorage instance. If None,
                        creates default storage from config/formulas.yaml.
    """
    # Create default storage if not provided
    if formula_storage is None:
        from src.infrastructure.persistence.formula_storage import FormulaStorage

        formula_storage = FormulaStorage()

    # Load all formulas
    try:
        stored_formulas = formula_storage.load_all()
    except Exception as e:
        logger.warning(f"Failed to load formulas from storage: {e}")
        return

    if not stored_formulas:
        logger.debug("No formulas found in storage")
        return

    # Register each formula
    loaded_count = 0
    for name, stored in stored_formulas.items():
        try:
            # Parse formula string to AST
            ast = parse(stored.formula)

            # Register in registry
            registry.register_formula(name, ast)
            logger.debug(f"Loaded formula from storage: {name}")
            loaded_count += 1

        except Exception as e:
            logger.warning(f"Failed to load formula {name}: {e}")

    if loaded_count > 0:
        logger.info(f"Loaded {loaded_count} formulas from storage")
