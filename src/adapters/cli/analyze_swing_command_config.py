"""
Shared swing command configuration and setup-catalog helper.

Neutral adapter module: both analyze_swing_commands.py (`saham analyze
swing`) and analyze_swing_compare_commands.py (`saham analyze
swing-compare`) import config and the setup catalog builder from here.
Neither command module owns the other's dependencies.

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
class AnalyzeSwingCommandConfig:
    swing_config: SwingConfig
    swing_backtest_config: SwingBacktestConfig
    analyze_swing_config: AnalyzeSwingConfig
    accumulation_screener_config: AccumulationScreenerConfig
    setup_config: SwingSetupCatalogConfig


def load_analyze_swing_command_config() -> AnalyzeSwingCommandConfig:
    swing_config = load_swing_config()
    return AnalyzeSwingCommandConfig(
        swing_config=swing_config,
        swing_backtest_config=load_swing_backtest_config(),
        analyze_swing_config=load_analyze_swing_config(),
        accumulation_screener_config=load_accumulation_screener_config(),
        setup_config=build_swing_setup_catalog_config(swing_config),
    )
