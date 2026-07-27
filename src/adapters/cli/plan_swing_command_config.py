"""
Shared swing command configuration and setup-catalog helper.

Adapter module for `saham plan swing` config loading and setup catalog.

Layer: Adapter
"""

from dataclasses import dataclass

from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.evaluate_swing_setup_use_case import SwingSetupCatalogConfig
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
    load_accumulation_screener_config,
)
from src.infrastructure.config.analyze_swing_config import (
    AnalyzeSwingConfig,
    load_analyze_swing_config,
)
from src.infrastructure.config.swing_backtest_config import (
    SwingBacktestConfig,
    load_swing_backtest_config,
)
from src.infrastructure.config.swing_config import SwingConfig, load_swing_config


@dataclass(frozen=True)
class PlanSwingCommandConfig:
    swing_config: SwingConfig
    swing_backtest_config: SwingBacktestConfig
    analyze_swing_config: AnalyzeSwingConfig
    accumulation_screener_config: AccumulationScreenerConfig
    setup_config: SwingSetupCatalogConfig


def load_plan_swing_command_config() -> PlanSwingCommandConfig:
    """Load all configs needed by plan swing command adapters."""
    swing_config = load_swing_config()
    return PlanSwingCommandConfig(
        swing_config=swing_config,
        swing_backtest_config=load_swing_backtest_config(),
        analyze_swing_config=load_analyze_swing_config(),
        accumulation_screener_config=load_accumulation_screener_config(),
        setup_config=build_swing_setup_catalog_config(swing_config),
    )
