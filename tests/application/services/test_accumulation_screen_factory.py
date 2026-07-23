from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.services.accumulation_screen_factory import (
    AccumulationScreenUseCaseBundle,
    create_accumulation_screen_use_case,
    create_accumulation_screen_use_case_bundle,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.record_accumulation_observations_use_case import (
    RecordAccumulationObservationsUseCase,
)
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
    make_signal_evidence_execution_context,
)


def test_create_accumulation_screen_use_case_wires_stockbit_providers():
    broker_repo = Mock()
    market_repo = Mock()
    risk_use_case = Mock()
    signal_engine = Mock()
    providers = SimpleNamespace(
        corp_repo=Mock(),
        season_prov=Mock(),
        insider_prov=Mock(),
        analyst_prov=Mock(),
        forward_estimates_prov=Mock(),
        shareholding_prov=Mock(),
        bandar_prov=Mock(),
        fundamentals_prov=Mock(),
        notation_prov=Mock(),
    )

    use_case = create_accumulation_screen_use_case(
        indicator_registry=IndicatorRegistry(),
        broker_repository=broker_repo,
        market_repository=market_repo,
        rules_loader=RulesYamlLoader(),
        stockbit_providers=providers,
        risk_use_case=risk_use_case,
        signal_engine=signal_engine,
        accum_score_policy=AccumScorePolicy(),
    )

    assert use_case._broker_repo is broker_repo
    assert use_case._market_repo is market_repo
    assert use_case._enricher._corp_action_repo is providers.corp_repo
    assert use_case._enricher._seasonality_provider is providers.season_prov
    assert use_case._enricher._insider_provider is providers.insider_prov
    assert use_case._enricher._analyst_provider is providers.analyst_prov
    assert use_case._enricher._forward_estimates_provider is providers.forward_estimates_prov
    assert use_case._enricher._shareholding_provider is providers.shareholding_prov
    assert use_case._enricher._bandar_provider is providers.bandar_prov
    assert use_case._structural_filter._fundamentals_provider is providers.fundamentals_prov
    assert use_case._enricher._ticker_notation_provider is providers.notation_prov
    assert use_case._risk_use_case is risk_use_case
    assert use_case._signal_engine is signal_engine


def test_accumulation_screen_use_case_does_not_build_its_own_recorder():
    """S1 boundary cleanup: AccumulationScreenUseCase must not know how to
    construct RecordAccumulationObservationsUseCase — that wiring belongs to
    the factory (create_accumulation_screen_use_case_bundle), not the screen
    use case itself."""
    assert not hasattr(AccumulationScreenUseCase, "build_observation_recorder")


def test_bundle_factory_supplies_screen_use_case_and_working_recorder():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    spy_repo = SpyCandidateObservationsRepository()

    bundle = create_accumulation_screen_use_case_bundle(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    assert isinstance(bundle, AccumulationScreenUseCaseBundle)
    assert isinstance(bundle.screen_use_case, AccumulationScreenUseCase)
    assert isinstance(bundle.record_observations_use_case, RecordAccumulationObservationsUseCase)

    request = AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        as_of_date=as_of,
    )

    # screen_use_case.execute() is read-only — no persistence side effect.
    response = bundle.screen_use_case.execute(
        request,
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert len(response.candidates) == 1
    assert spy_repo.saved == []

    # The bundle's recorder is the sole intentional persistence entrypoint.
    result = bundle.record_observations_use_case.execute(
        request,
        execution_context=make_signal_evidence_execution_context(as_of),
    )
    assert result.recorded_count == 1
    assert len(spy_repo.saved) == 1
    assert spy_repo.saved[0].ticker == "BBCA"


def test_bundle_factory_shares_one_signal_engine_instance_across_screen_and_persister():
    """HIGH-2 Finding 1: create_accumulation_screen_use_case_bundle() must not
    construct a second, independently-configured SignalEngine for the
    observation persister's evidence builder — the screen use case and the
    persister's AccumulationCandidateEvidenceBuilder must own the exact same
    injected instance, never separate screen/persistence engines."""
    engine = SignalEngine(config=SignalEngineConfig())

    bundle = create_accumulation_screen_use_case_bundle(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository([]),
        market_repository=MockMarketRepository([]),
        rules_loader=FakeRulesLoader(),
        signal_engine=engine,
    )

    assert bundle.screen_use_case._signal_engine is engine
    persister = bundle.record_observations_use_case._observation_persister
    assert persister._candidate_evidence_builder._signal_engine is engine
