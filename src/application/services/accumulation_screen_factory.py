"""
Accumulation screen use-case construction helpers.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.ports.rules_loader import RulesLoader
from src.application.services.accumulation_candidate_evidence_builder import (
    AccumulationCandidateEvidenceBuilder,
)
from src.application.services.accumulation_candidate_observation_persister import (
    AccumulationCandidateObservationPersister,
)
from src.application.services.primary_setup_family_resolver import (
    PrimarySetupFamilyResolver,
)
from src.application.services.relative_strength_calculator import (
    RelativeStrengthCalculator,
)
from src.application.services.signal_engine import SignalEngine
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.record_accumulation_observations_use_case import (
    RecordAccumulationObservationsUseCase,
)
from src.application.use_case.score_foreign_flow_use_case import (
    ScoreForeignFlowUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


def create_accumulation_screen_use_case(
    *,
    broker_repository: BrokerDataRepository,
    market_repository: MarketDataRepository,
    indicator_registry: Any,
    rules_loader: RulesLoader,
    stockbit_providers: Any | None = None,
    risk_use_case: Any | None = None,
    signal_engine: Any | None = None,
    candidate_observations_repository: Any | None = None,
    foreign_flow_score_policy: Any | None = None,
    derived_feature_policy: Any | None = None,
    idx_groups: dict[str, list[str]] | None = None,
    swing_setup_catalog: Any | None = None,
    ticker_profile_classifier_factory: Any | None = None,
    institutional_accumulation_config_factory: Any | None = None,
    sector_context_builder_factory: Any | None = None,
    company_quality_context_builder_factory: Any | None = None,
) -> AccumulationScreenUseCase:
    """Build AccumulationScreenUseCase with consistent optional enrichment wiring.

    rules_loader must be supplied by the caller's adapter/composition root
    with a concrete implementation from the infrastructure layer, so
    strategy-evidence lookups keep working when request.strategy_name is set.
    """
    score_use_case = (
        ScoreForeignFlowUseCase(foreign_flow_score_policy)
        if foreign_flow_score_policy is not None
        else None
    )
    return AccumulationScreenUseCase(
        broker_repository=broker_repository,
        market_repository=market_repository,
        indicator_registry=indicator_registry,
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
        rules_loader=rules_loader,
        ticker_profile_classifier_factory=ticker_profile_classifier_factory,
        institutional_accumulation_config_factory=institutional_accumulation_config_factory,
        sector_context_builder_factory=sector_context_builder_factory,
        company_quality_context_builder_factory=company_quality_context_builder_factory,
    )


@dataclass(frozen=True)
class AccumulationScreenUseCaseBundle:
    """A read-only screen use case paired with its canonical observation recorder.

    The recorder is a separate, explicit collaborator — never reached through
    the screen use case itself. Only wire record_observations_use_case into
    explicit observation-generation callers (e.g. signal-backfill); ordinary
    manual screens, --multi, screen compare, and DailyBriefingUseCase must use
    screen_use_case only.
    """

    screen_use_case: AccumulationScreenUseCase
    record_observations_use_case: RecordAccumulationObservationsUseCase


def create_accumulation_screen_use_case_bundle(
    *,
    broker_repository: BrokerDataRepository,
    market_repository: MarketDataRepository,
    indicator_registry: Any,
    rules_loader: RulesLoader,
    stockbit_providers: Any | None = None,
    risk_use_case: Any | None = None,
    signal_engine: Any | None = None,
    candidate_observations_repository: Any | None = None,
    foreign_flow_score_policy: Any | None = None,
    derived_feature_policy: Any | None = None,
    idx_groups: dict[str, list[str]] | None = None,
    swing_setup_catalog: Any | None = None,
    ticker_profile_classifier_factory: Any | None = None,
    institutional_accumulation_config_factory: Any | None = None,
    sector_context_builder_factory: Any | None = None,
    company_quality_context_builder_factory: Any | None = None,
) -> AccumulationScreenUseCaseBundle:
    """Build the screen use case together with its canonical observation recorder.

    Accepts the same wiring as create_accumulation_screen_use_case() and
    additionally constructs the AccumulationCandidateObservationPersister the
    recorder needs. AccumulationCandidateEvidenceBuilder and its collaborators
    are stateless, config-only services (no per-request state), so building an
    equivalently-configured instance here — from the same inputs
    AccumulationScreenUseCase.__init__ uses internally — behaves identically
    to reusing the screen's own instance, without the screen use case having
    to build or expose it.

    Only intended for explicit observation-generation callers (e.g.
    signal-backfill). Never wire record_observations_use_case into
    diagnostic/read-only paths (--multi, screen compare, DailyBriefingUseCase,
    plain manual screens).
    """
    screen_use_case = create_accumulation_screen_use_case(
        broker_repository=broker_repository,
        market_repository=market_repository,
        indicator_registry=indicator_registry,
        rules_loader=rules_loader,
        stockbit_providers=stockbit_providers,
        risk_use_case=risk_use_case,
        signal_engine=signal_engine,
        candidate_observations_repository=candidate_observations_repository,
        foreign_flow_score_policy=foreign_flow_score_policy,
        derived_feature_policy=derived_feature_policy,
        idx_groups=idx_groups,
        swing_setup_catalog=swing_setup_catalog,
        ticker_profile_classifier_factory=ticker_profile_classifier_factory,
        institutional_accumulation_config_factory=institutional_accumulation_config_factory,
        sector_context_builder_factory=sector_context_builder_factory,
        company_quality_context_builder_factory=company_quality_context_builder_factory,
    )

    setup_family_resolver = PrimarySetupFamilyResolver()
    candidate_evidence_builder = AccumulationCandidateEvidenceBuilder(
        market_repository=market_repository,
        broker_repository=broker_repository,
        signal_engine=signal_engine or SignalEngine(),
        candidate_observations_repository=candidate_observations_repository,
        swing_setup_catalog=swing_setup_catalog,
        primary_setup_family_resolver=setup_family_resolver,
        relative_strength_calculator=RelativeStrengthCalculator(),
        indicator_registry=indicator_registry,
        rules_loader=rules_loader,
        ticker_profile_classifier_factory=ticker_profile_classifier_factory,
        institutional_accumulation_config_factory=institutional_accumulation_config_factory,
        sector_context_builder_factory=sector_context_builder_factory,
        company_quality_context_builder_factory=company_quality_context_builder_factory,
    )
    observation_persister = AccumulationCandidateObservationPersister(
        candidate_observations_repository=candidate_observations_repository,
        candidate_evidence_builder=candidate_evidence_builder,
        setup_family_resolver=setup_family_resolver,
        swing_setup_catalog=swing_setup_catalog,
    )
    record_observations_use_case = RecordAccumulationObservationsUseCase(
        screen_use_case=screen_use_case,
        observation_persister=observation_persister,
    )

    return AccumulationScreenUseCaseBundle(
        screen_use_case=screen_use_case,
        record_observations_use_case=record_observations_use_case,
    )
