"""
Helper for constructing configured risk engines in the CLI adapter.

Layer: Adapter
"""

from pathlib import Path

from src.application.services.bootstrap import create_risk_engine
from src.application.services.risk_engine import RiskEngine
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.engine_config_loader import load_engine_config


def create_configured_risk_engine(
    db_path: Path,
    with_enrichment: bool = False,
    rules_loader=None,
) -> RiskEngine:
    """Load the production risk configuration and build the risk engine."""
    config = load_engine_config(Path(APP_CFG.config_paths.risk_engine))
    return create_risk_engine(
        db_path=db_path,
        with_enrichment=with_enrichment,
        rules_loader=rules_loader,
        config=config,
    )
