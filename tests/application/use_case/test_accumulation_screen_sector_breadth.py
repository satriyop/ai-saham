"""Sector, relative strength, and volatility context behavior tests for screening."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.institutional_accumulation_evidence import (
    EvidenceStatus,
)
from src.domain.value_objects.sector_context_evidence import (
    SectorContextEvidence,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    EmptyATRRegistry,
    FakeATRRegistry,
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    RaisingATRRegistry,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
    execute_and_record,
)


def test_screen_persists_sector_context_fingerprint_when_builder_available():
    class FakeSectorContextBuilder:
        def peers_for_ticker(self, ticker):
            return ("BBRI",)

        def build(self, request):
            return SectorContextEvidence(
                sector="banking",
                peer_count=1,
                peer_tickers=("BBRI",),
                sector_20d_return=0.02,
                sector_vs_ihsg_20d=0.01,
                sector_breadth=1.0,
                ticker_vs_sector_rs=0.01,
                sector_regime="BULLISH",
                coverage_score=1.0,
                evidence_status=EvidenceStatus.DIAGNOSTIC,
                reasons=(),
                unavailable_reasons=(),
            )

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ] + [
        _candle("IHSG", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
        for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        sector_context_builder_factory=lambda: FakeSectorContextBuilder(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    execute_and_record(
        use_case,
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
    )

    fingerprint = spy_repo.saved[0].payload["sub_signal_fingerprint"]
    assert fingerprint["sc_sector"] == "banking"
    assert fingerprint["sc_sector_regime"] == "BULLISH"
    assert fingerprint["sc_sector_vs_ihsg_20d"] == pytest.approx(0.01)


def test_screen_persists_benchmark_excess_return_as_diagnostic_evidence():
    """Benchmark excess return flows end-to-end: BenchmarkExcessReturnCalculator
    computes real values from BBCA + IHSG candles seeded in the same
    MockMarketRepository, and the typed evidence is persisted in
    sub_signal_fingerprint (benchmark_excess_return_5_session /
    benchmark_excess_return_20_session) with an explicit
    DIAGNOSTIC_UNVALIDATED authority status. Task HIGH-1 removed the
    production rs_policy authority path entirely, so no rs_policy_* reason
    string may appear in phase_reasons regardless of the measured value.

    Uses a 2026 as_of_date so SetupEvidenceBuilder's own freshness gate
    (_IHSG_AVAILABLE_FROM = 2025-07-01) does not force the evidence back to
    UNAVAILABLE before SetupPhaseDetector sees it.

    A loosened coiled-spring swing_setup_catalog (family="breakout") is
    injected -- same technique as
    test_screen_persists_setup_family_fingerprint_when_swing_setup_catalog_matches
    -- so the candidate resolves to setup_family="breakout".
    """
    from src.application.use_case.evaluate_swing_setup_use_case import (
        CoiledSpringSetupConfig,
        ForeignBounceSetupConfig,
        PullbackContinuationSetupConfig,
        SmartMoneyConfirmedSetupConfig,
        SwingSetupCatalogConfig,
    )

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]

    # 130 days of varied (non-flat), rising-faster-than-benchmark closes for
    # both BBCA and IHSG so a real, non-None RS is computed for both windows.
    base_dates = [date(2025, 9, 1) + timedelta(days=i) for i in range(130)]
    bbca_candles = [
        _candle("BBCA", d, Decimal("100") + Decimal(i % 5) + Decimal(i) * Decimal("0.05"))
        for i, d in enumerate(base_dates)
    ]
    ihsg_candles = [
        _candle("IHSG", d, Decimal("100") + Decimal(i) * Decimal("0.01"))
        for i, d in enumerate(base_dates)
    ]
    candles = bbca_candles + ihsg_candles
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    swing_setup_catalog = SwingSetupCatalogConfig(
        foreign_bounce=ForeignBounceSetupConfig(enabled=False, family="foreign_bounce"),
        coiled_spring=CoiledSpringSetupConfig(
            gate_min_foreign_flow_score=0.0,
            gate_max_bb_width_pctile=1.0,
            gate_min_flow_ratio_pct=-100.0,
            gate_max_rsi=100.0,
            family="breakout",
        ),
        smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
            enabled=False, family="confirmation"
        ),
        pullback_continuation=PullbackContinuationSetupConfig(
            enabled=False, family="pullback"
        ),
    )

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        swing_setup_catalog=swing_setup_catalog,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = execute_and_record(
        use_case,
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]

    assert fingerprint["benchmark_excess_return_5_session"] is not None
    assert fingerprint["benchmark_excess_return_20_session"] is not None
    assert fingerprint["benchmark_excess_return_5_session"]["status"] == "AVAILABLE"
    assert fingerprint["benchmark_excess_return_20_session"]["status"] == "AVAILABLE"
    assert fingerprint["benchmark_excess_return_authority_status"] == "DIAGNOSTIC_UNVALIDATED"
    # The removed production authority path must never surface a reason.
    assert not any(
        reason.startswith("rs_policy") for reason in fingerprint["phase_reasons"]
    )


def test_screen_benchmark_excess_return_unavailable_when_ihsg_candles_missing():
    """Regression: when no IHSG candles exist at all in the market repository,
    BenchmarkExcessReturnCalculator resolves both windows to UNAVAILABLE
    (insufficient aligned closes) rather than raising, and the screen still
    completes normally with the typed evidence explicitly UNAVAILABLE — never
    neutral, zero, or omitted."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),  # no IHSG candles seeded
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = execute_and_record(
        use_case,
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]
    assert fingerprint["benchmark_excess_return_5_session"]["status"] == "UNAVAILABLE"
    assert fingerprint["benchmark_excess_return_20_session"]["status"] == "UNAVAILABLE"
    assert fingerprint["benchmark_excess_return_5_session"]["excess_return_pct"] is None
    assert fingerprint["benchmark_excess_return_20_session"]["excess_return_pct"] is None


def test_screen_persists_volatility_context_fingerprint_from_injected_registry():
    """When indicator_registry is injected, the persisted sub_signal_fingerprint
    carries atr_at_signal/atr_pct_at_signal/volatility_bucket_at_signal/
    volatility_size_multiplier_at_signal consistent with build_volatility_context
    given ATR=5 (from FakeATRRegistry) and the candidate's current_price (100,
    per the _candle fixture's close)."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
        indicator_registry=FakeATRRegistry(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = execute_and_record(
        use_case,
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
    )

    assert len(response.candidates) == 1
    assert response.candidates[0].current_price == Decimal("100")
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]

    # ATR=5, close=100 -> atr_pct = 5.0 -> HIGH bucket (condition is `< 5.0`,
    # so exactly 5.0 falls into HIGH, not NORMAL), multiplier 0.75.
    assert fingerprint["atr_at_signal"] == 5.0
    assert fingerprint["atr_pct_at_signal"] == 5.0
    assert fingerprint["volatility_bucket_at_signal"] == "HIGH"
    assert fingerprint["volatility_size_multiplier_at_signal"] == 0.75


def test_screen_volatility_context_falls_back_to_unknown_when_atr_unavailable():
    """Whether the registry returns an empty ATR series (insufficient candle
    history) or raises outright, _build_candidate_volatility_context must
    never propagate a failure: the candidate observation still saves,
    screen_result stays 'pass', and the volatility fingerprint resolves to
    UNKNOWN/None/None/1.0 (build_volatility_context's atr_value=None path)."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]

    for registry in (EmptyATRRegistry(), RaisingATRRegistry()):
        candles = [
            _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
            for i in range(45)
        ]
        summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

        spy_repo = SpyCandidateObservationsRepository()
        use_case = AccumulationScreenUseCase(
            broker_repository=MockBrokerRepository(summaries),
            market_repository=MockMarketRepository(candles),
            rules_loader=FakeRulesLoader(),
            candidate_observations_repository=spy_repo,
            indicator_registry=registry,
            signal_engine=SignalEngine(config=SignalEngineConfig()),
        )

        response = execute_and_record(
            use_case,
            AccumulationScreenRequest(
                tickers=["BBCA"],
                window_days=7,
                min_net_buy_days=1,
                as_of_date=as_of,
            ),
        )

        assert len(response.candidates) == 1
        assert len(spy_repo.saved) == 1

        obs = spy_repo.saved[0]
        assert isinstance(obs, CandidateObservation)
        assert obs.payload["screen_result"] == "pass"

        fingerprint = obs.payload["sub_signal_fingerprint"]
        assert fingerprint["atr_at_signal"] is None
        assert fingerprint["atr_pct_at_signal"] is None
        assert fingerprint["volatility_bucket_at_signal"] == "UNKNOWN"
        assert fingerprint["volatility_size_multiplier_at_signal"] == 1.0


def test_volatility_context_fingerprint_never_leaks_into_scoring():
    """Regression guard: the injected indicator_registry (used only to build
    the volatility-context fingerprint) must not affect scoring/verdict.
    Running the exact same screen twice — once with FakeATRRegistry (ATR=5)
    and once with EmptyATRRegistry (no ATR) — must produce an IDENTICAL
    signal_assessment (score/strength/entry_quality), foreign_flow_score, and
    trade_setup for the same candidate. Only the volatility fields inside
    sub_signal_fingerprint may differ between the two persisted observations.
    """
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]

    def _fresh_candles():
        return [
            _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
            for i in range(45)
        ]

    def _fresh_summaries():
        return [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo_a = SpyCandidateObservationsRepository()
    use_case_a = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(_fresh_summaries()),
        market_repository=MockMarketRepository(_fresh_candles()),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo_a,
        indicator_registry=FakeATRRegistry(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    response_a = execute_and_record(
        use_case_a,
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
    )

    spy_repo_b = SpyCandidateObservationsRepository()
    use_case_b = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(_fresh_summaries()),
        market_repository=MockMarketRepository(_fresh_candles()),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo_b,
        indicator_registry=EmptyATRRegistry(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    response_b = execute_and_record(
        use_case_b,
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
    )

    assert len(response_a.candidates) == 1
    assert len(response_b.candidates) == 1
    candidate_a = response_a.candidates[0]
    candidate_b = response_b.candidates[0]

    assert candidate_a.foreign_flow_score == candidate_b.foreign_flow_score
    assert candidate_a.signal_assessment is not None
    assert candidate_b.signal_assessment is not None
    assert (
        candidate_a.signal_assessment.assessment.score
        == candidate_b.signal_assessment.assessment.score
    )
    assert (
        candidate_a.signal_assessment.assessment.strength
        == candidate_b.signal_assessment.assessment.strength
    )
    assert (
        candidate_a.signal_assessment.assessment.entry_quality
        == candidate_b.signal_assessment.assessment.entry_quality
    )
    assert candidate_a.trade_setup == candidate_b.trade_setup

    assert len(spy_repo_a.saved) == 1
    assert len(spy_repo_b.saved) == 1
    obs_a = spy_repo_a.saved[0]
    obs_b = spy_repo_b.saved[0]
    assert isinstance(obs_a, CandidateObservation)
    assert isinstance(obs_b, CandidateObservation)

    fingerprint_a = dict(obs_a.payload["sub_signal_fingerprint"])
    fingerprint_b = dict(obs_b.payload["sub_signal_fingerprint"])

    volatility_keys = {
        "atr_at_signal",
        "atr_pct_at_signal",
        "volatility_bucket_at_signal",
    }
    for key in volatility_keys:
        assert fingerprint_a[key] != fingerprint_b[key], (
            f"expected {key} to differ between runs, both were {fingerprint_a[key]!r}"
        )
    assert fingerprint_a["volatility_bucket_at_signal"] == "HIGH"
    assert fingerprint_b["volatility_bucket_at_signal"] == "UNKNOWN"
