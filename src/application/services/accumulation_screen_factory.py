"""
Accumulation screen use-case construction helpers.

Layer: Application
"""

from __future__ import annotations

from typing import Any

from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.score_foreign_flow_use_case import (
    ScoreForeignFlowUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


def create_accumulation_screen_use_case(
    *,
    broker_repository: BrokerDataRepository,
    market_repository: MarketDataRepository,
    stockbit_providers: Any | None = None,
    risk_use_case: Any | None = None,
    signal_engine: Any | None = None,
    candidate_observations_repository: Any | None = None,
    foreign_flow_score_policy: Any | None = None,
    derived_feature_policy: Any | None = None,
    idx_groups: dict[str, list[str]] | None = None,
    swing_setup_catalog: Any | None = None,
) -> AccumulationScreenUseCase:
    """Build AccumulationScreenUseCase with consistent optional enrichment wiring."""
    score_use_case = (
        ScoreForeignFlowUseCase(foreign_flow_score_policy)
        if foreign_flow_score_policy is not None
        else None
    )
    return AccumulationScreenUseCase(
        broker_repository=broker_repository,
        market_repository=market_repository,
        corporate_action_repo=getattr(stockbit_providers, "corp_repo", None),
        seasonality_provider=getattr(stockbit_providers, "season_prov", None),
        insider_activity_provider=getattr(stockbit_providers, "insider_prov", None),
        analyst_consensus_provider=getattr(stockbit_providers, "analyst_prov", None),
        forward_estimates_provider=getattr(stockbit_providers, "forward_estimates_prov", None),
        shareholding_provider=getattr(stockbit_providers, "shareholding_prov", None),
        bandar_detector_provider=getattr(stockbit_providers, "bandar_prov", None),
        fundamentals_provider=getattr(stockbit_providers, "fundamentals_prov", None),
        ticker_notation_provider=getattr(stockbit_providers, "notation_prov", None),
        idx_groups=idx_groups,
        risk_use_case=risk_use_case,
        signal_engine=signal_engine,
        candidate_observations_repository=candidate_observations_repository,
        foreign_flow_score_use_case=score_use_case,
        derived_feature_policy=derived_feature_policy,
        swing_setup_catalog=swing_setup_catalog,
    )
