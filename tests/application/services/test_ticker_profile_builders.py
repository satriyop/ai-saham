"""Focused tests for evidence builders and their ticker profile classification."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from src.application.services.accumulation_candidate_evidence_builder import (
    AccumulationCandidateEvidenceBuilder,
)
from src.application.services.swing_analysis_evidence_builder import (
    SwingAnalysisEvidenceBuilder,
)
from src.domain.value_objects.ticker_profile_snapshot import TickerProfileSnapshot
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader


def test_accumulation_candidate_evidence_builder_no_factory():
    # 1. accumulation_candidate_evidence_builder.py does not import infrastructure
    # and returns None when no ticker profile factory is provided.
    builder = AccumulationCandidateEvidenceBuilder(
        market_repository=MagicMock(),
        broker_repository=MagicMock(),
        signal_engine=None,
        candidate_observations_repository=None,
        swing_setup_catalog=None,
        primary_setup_family_resolver=MagicMock(),
        relative_strength_calculator=MagicMock(),
        indicator_registry=MagicMock(),
        ticker_profile_classifier_factory=None,
    )
    candidate = MagicMock()
    candidate.ticker = "BBCA"
    candidate.fundamentals = None
    candidate.ticker_notation = None

    res = builder.build_candidate_ticker_profile(candidate, date(2026, 6, 1))
    assert res is None


def test_accumulation_candidate_evidence_builder_with_fake_factory():
    # 2. when a fake classifier factory is injected, ticker profile classification is used.
    mock_snapshot = MagicMock(spec=TickerProfileSnapshot)
    mock_classifier = MagicMock()
    mock_classifier.classify.return_type = mock_snapshot
    mock_classifier.classify.return_value = mock_snapshot

    def fake_factory():
        return mock_classifier

    market_mock = MagicMock()
    market_mock.get_candles.return_value = []
    broker_mock = MagicMock()
    broker_mock.get_broker_daily_flows.return_value = ()
    broker_mock.get_broker_summaries.return_value = ()

    builder = AccumulationCandidateEvidenceBuilder(
        market_repository=market_mock,
        broker_repository=broker_mock,
        signal_engine=None,
        candidate_observations_repository=None,
        swing_setup_catalog=None,
        primary_setup_family_resolver=MagicMock(),
        relative_strength_calculator=MagicMock(),
        indicator_registry=MagicMock(),
        ticker_profile_classifier_factory=fake_factory,
    )
    candidate = MagicMock()
    candidate.ticker = "BBCA"
    candidate.fundamentals = None
    candidate.ticker_notation = None

    res = builder.build_candidate_ticker_profile(candidate, date(2026, 6, 1))
    assert res is mock_snapshot
    mock_classifier.classify.assert_called_once()


def test_swing_analysis_evidence_builder_no_factory():
    builder = SwingAnalysisEvidenceBuilder(
        market_repository=MagicMock(),
        broker_repository=MagicMock(),
        registry=MagicMock(),
        rules_loader=RulesYamlLoader(),
        flow_confirmation_builder=MagicMock(),
        candidate_observations_repository=None,
        signal_engine=None,
        corporate_action_risk_use_case=None,
        ticker_profile_classifier_factory=None,
    )
    res = builder.build(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 1),
        benchmark="IHSG",
        candles=[],
        accumulation_candidate=None,
        setup_eval=None,
        setup_name=None,
        strategy_name=None,
        swing_config=None,
    )
    assert res.ticker_profile_snapshot is None


def test_swing_analysis_evidence_builder_with_fake_factory():
    # 3. swing_analysis_evidence_builder.py uses injected fake classifier factory.
    mock_snapshot = MagicMock(spec=TickerProfileSnapshot)
    mock_classifier = MagicMock()
    mock_classifier.classify.return_type = mock_snapshot
    mock_classifier.classify.return_value = mock_snapshot

    def fake_factory():
        return mock_classifier

    broker_mock = MagicMock()
    broker_mock.get_broker_daily_flows.return_value = ()
    broker_mock.get_broker_summaries.return_value = ()

    builder = SwingAnalysisEvidenceBuilder(
        market_repository=MagicMock(),
        broker_repository=broker_mock,
        registry=MagicMock(),
        rules_loader=RulesYamlLoader(),
        flow_confirmation_builder=MagicMock(),
        candidate_observations_repository=None,
        signal_engine=None,
        corporate_action_risk_use_case=None,
        ticker_profile_classifier_factory=fake_factory,
    )
    res = builder.build(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 1),
        benchmark="IHSG",
        candles=[],
        accumulation_candidate=None,
        setup_eval=None,
        setup_name=None,
        strategy_name=None,
        swing_config=None,
    )
    assert res.ticker_profile_snapshot is mock_snapshot
    mock_classifier.classify.assert_called_once()
