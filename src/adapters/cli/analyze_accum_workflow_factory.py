"""
Factory for the `saham analyze accum-audit` workflow.

Layer: Adapter

Owns CLI/infrastructure wiring (config loaders, SQLite repositories, indicator
registry, rules loader, and universe resolution) so analyze_accum_commands.py
can stay focused on flag parsing, request construction, execution, and
rendering.
"""

from __future__ import annotations

from pathlib import Path

from src.application.services.universe_loader import resolve_tickers
from src.application.use_case.accumulation_audit_use_case import AccumulationAuditUseCase
from src.application.use_case.run_accumulation_audit_workflow_use_case import (
    RunAccumulationAuditWorkflowUseCase,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.config.accumulation_audit_config import (
    load_accumulation_audit_config,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.composition.signal_engine_factory import create_signal_engine
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def create_run_accumulation_audit_workflow(
    *,
    db_path: Path,
) -> RunAccumulationAuditWorkflowUseCase:
    """Build the accumulation-audit workflow use case with CLI infrastructure."""
    cfg_audit = load_accumulation_audit_config()
    cfg_screen = load_accumulation_screener_config()
    broker_repository = SQLiteBrokerRepository(db_path)

    audit_use_case = AccumulationAuditUseCase(
        broker_repository=broker_repository,
        market_repository=SQLiteMarketRepository(db_path=db_path),
        indicator_registry=create_indicator_registry(),
        rules_loader=RulesYamlLoader(),
        signal_engine=create_signal_engine(db_path=db_path, with_enrichment=True),
        derived_feature_policy=cfg_screen.derived_features,
    )

    def _resolve_tickers(*, universe: str | None, explicit: list[str]) -> list[str]:
        return resolve_tickers(
            universe=universe,
            explicit=explicit,
            db_path=db_path,
            loader=YamlUniverseConfigLoader(),
            repository=broker_repository,
        )

    return RunAccumulationAuditWorkflowUseCase(
        audit_use_case=audit_use_case,
        audit_policy=cfg_audit.policy,
        audit_setups=cfg_audit.setups,
        resolve_tickers=_resolve_tickers,
    )
