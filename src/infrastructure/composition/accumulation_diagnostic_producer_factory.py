"""Resolve one typed diagnostic-producer graph for corpus capture.

Layer: Infrastructure composition. This module owns config I/O and returns
typed objects/factories; it owns no identity or workflow policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.application.services.accumulation_diagnostic_producer_payloads import (
    AccumulationDiagnosticProducerInputs,
)
from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextEvidenceBuilder,
)
from src.application.services.institutional_flow_config import (
    InstitutionalAccumulationConfig,
)
from src.application.services.sector_context_evidence_builder import (
    SectorContextEvidenceBuilder,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.services.ticker_profile_classifier import TickerProfileClassifier
from src.infrastructure.config.app_config import ConfigPathsConfig
from src.infrastructure.config.company_quality_context_config_loader import (
    load_company_quality_context_config,
)
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.config.market_context_config import load_market_context_config
from src.infrastructure.config.sector_context_config_loader import (
    build_sector_universe_index,
    load_sector_context_config,
)
from src.infrastructure.config.ticker_profile_config_loader import (
    load_ticker_profile_config,
    load_ticker_universe_index,
)


@dataclass(frozen=True)
class AccumulationDiagnosticProducerRuntime:
    inputs: AccumulationDiagnosticProducerInputs
    ticker_profile_classifier_factory: Callable[[], TickerProfileClassifier]
    institutional_accumulation_config_factory: Callable[[], InstitutionalAccumulationConfig]
    sector_context_builder_factory: Callable[[], SectorContextEvidenceBuilder]
    company_quality_context_builder_factory: Callable[[], CompanyQualityContextEvidenceBuilder]


def resolve_accumulation_diagnostic_producer_runtime(
    *,
    signal_engine_config: SignalEngineConfig,
    market_context_universe: tuple[str, ...],
    config_paths: ConfigPathsConfig,
) -> AccumulationDiagnosticProducerRuntime:
    """Load producer inputs once and bind the exact objects into live builders."""

    sector_config = load_sector_context_config(config_paths.sector_context)
    sector_index_dict = build_sector_universe_index(config_paths.universes)
    sector_index = tuple(
        (str(group), tuple(str(ticker) for ticker in tickers))
        for group, tickers in sector_index_dict.items()
    )
    institutional_config = load_institutional_accumulation_config(
        config_paths.institutional_accumulation
    )
    company_config = load_company_quality_context_config(config_paths.company_quality_context)
    ticker_config = load_ticker_profile_config(config_paths.ticker_profile)
    ticker_index_dict = load_ticker_universe_index(config_paths.universes)
    ticker_index = tuple(
        (str(ticker), tuple(str(group) for group in groups))
        for ticker, groups in ticker_index_dict.items()
    )
    market_context_config = load_market_context_config(Path(config_paths.market_context_engine))

    inputs = AccumulationDiagnosticProducerInputs(
        alpha_trigger_config=signal_engine_config.alpha_trigger,
        sector_context_config=sector_config,
        sector_universe_index=sector_index,
        institutional_accumulation_config=institutional_config,
        company_quality_context_config=company_config,
        signal_scoring_config=signal_engine_config.scoring,
        company_quality_neutral_score=50.0,
        ticker_profile_config=ticker_config,
        ticker_universe_index=ticker_index,
        market_context_config=market_context_config,
        market_context_universe=tuple(market_context_universe),
    )

    def ticker_profile_factory() -> TickerProfileClassifier:
        return TickerProfileClassifier(
            config=ticker_config,
            ticker_universe_index=dict(ticker_index),
        )

    def institutional_factory() -> InstitutionalAccumulationConfig:
        return institutional_config

    def sector_factory() -> SectorContextEvidenceBuilder:
        return SectorContextEvidenceBuilder(sector_config, dict(sector_index))

    def company_factory() -> CompanyQualityContextEvidenceBuilder:
        return CompanyQualityContextEvidenceBuilder(
            company_config,
            scoring=signal_engine_config.scoring,
            neutral_score=50.0,
        )

    return AccumulationDiagnosticProducerRuntime(
        inputs=inputs,
        ticker_profile_classifier_factory=ticker_profile_factory,
        institutional_accumulation_config_factory=institutional_factory,
        sector_context_builder_factory=sector_factory,
        company_quality_context_builder_factory=company_factory,
    )
