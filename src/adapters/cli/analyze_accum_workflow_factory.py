"""
Factory for the `saham research accumulation evaluate` workflow.

Layer: Adapter

Owns CLI/infrastructure wiring (config loaders, SQLite repositories, indicator
registry, rules loader, and universe resolution) so analyze_accum_commands.py
can stay focused on flag parsing, request construction, execution, and
rendering.
"""

from __future__ import annotations

from pathlib import Path

from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
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
    """Build the accumulation-audit workflow use case with CLI infrastructure.

    Screen construction uses ``create_accumulation_screen_use_case`` — the same
    factory live screen uses — with screener foreign-flow policy (DQ-008 D8-1).
    Enrichment providers and risk funnel remain off for historical lean replay.
    """
    cfg_audit = load_accumulation_audit_config()
    cfg_screen = load_accumulation_screener_config()
    broker_repository = SQLiteBrokerRepository(db_path)
    market_repository = SQLiteMarketRepository(db_path=db_path)
    indicator_registry = create_indicator_registry()
    rules_loader = RulesYamlLoader()
    signal_engine = create_signal_engine(db_path=db_path, with_enrichment=True)

    screen_use_case = create_accumulation_screen_use_case(
        broker_repository=broker_repository,
        market_repository=market_repository,
        indicator_registry=indicator_registry,
        rules_loader=rules_loader,
        signal_engine=signal_engine,
        accum_score_policy=cfg_screen.accum_score_policy,
        derived_feature_policy=cfg_screen.derived_features,
        stockbit_providers=None,
        risk_use_case=None,
    )

    audit_use_case = AccumulationAuditUseCase(
        broker_repository=broker_repository,
        market_repository=market_repository,
        indicator_registry=indicator_registry,
        rules_loader=rules_loader,
        signal_engine=signal_engine,
        derived_feature_policy=cfg_screen.derived_features,
        screen_use_case=screen_use_case,
        accum_score_policy=cfg_screen.accum_score_policy,
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
