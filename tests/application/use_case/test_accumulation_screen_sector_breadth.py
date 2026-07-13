"""Sector, relative strength, and volatility context behavior tests for screening."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
)
from src.application.services.indicator_registry import IndicatorRegistry
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
    MockBrokerRepository,
    MockMarketRepository,
    RaisingATRRegistry,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
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
        candidate_observations_repository=spy_repo,
        sector_context_builder_factory=lambda: FakeSectorContextBuilder(),
    )

    use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    fingerprint = spy_repo.saved[0].payload["sub_signal_fingerprint"]
    assert fingerprint["sc_sector"] == "banking"
    assert fingerprint["sc_sector_regime"] == "BULLISH"
    assert fingerprint["sc_sector_vs_ihsg_20d"] == pytest.approx(0.01)


def test_screen_persists_relative_strength_and_evaluates_rs_policy():
    """RS vs IHSG flows end-to-end: RelativeStrengthCalculator computes real
    values from BBCA + IHSG candles seeded in the same MockMarketRepository,
    the raw values are persisted in sub_signal_fingerprint
    (rs_vs_ihsg_20d_at_signal / rs_vs_ihsg_5d_at_signal), and the 5d value
    flows through SetupEvidenceBuilder/SetupPhaseDetector far enough that the
    RS policy (keyed by setup family) is genuinely evaluated rather than
    short-circuiting on "no policy for this family" / "no RS available".

    Uses a 2026 as_of_date so SetupEvidenceBuilder's own freshness gate
    (_IHSG_AVAILABLE_FROM = 2025-07-01) does not force rs_vs_ihsg_5d back to
    None before SetupPhaseDetector sees it.

    A loosened coiled-spring swing_setup_catalog (family="breakout") is
    injected -- same technique as
    test_screen_persists_setup_family_fingerprint_when_swing_setup_catalog_matches
    -- so the candidate resolves to setup_family="breakout", for which
    SetupPhaseConfig's default rs_policy_by_setup_family has a real entry,
    making cfg.rs_policy_for("breakout") non-None.
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
        candidate_observations_repository=spy_repo,
        swing_setup_catalog=swing_setup_catalog,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]

    assert fingerprint["rs_vs_ihsg_20d_at_signal"] is not None
    assert fingerprint["rs_vs_ihsg_5d_at_signal"] is not None
    assert "rs_policy_unavailable" not in fingerprint["phase_reasons"]
    assert any(
        reason == "rs_policy_passed" or reason.startswith("rs_policy_warning")
        or reason.startswith("rs_policy_hard_exclude")
        for reason in fingerprint["phase_reasons"]
    )


def test_screen_rs_fields_stay_none_when_ihsg_candles_missing():
    """Regression: when no IHSG candles exist at all in the market repository,
    RelativeStrengthCalculator resolves both windows to None (insufficient
    benchmark candles) rather than raising, and the screen still completes
    normally with the RS fingerprint fields set to None."""
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
        candidate_observations_repository=spy_repo,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]
    assert fingerprint["rs_vs_ihsg_20d_at_signal"] is None
    assert fingerprint["rs_vs_ihsg_5d_at_signal"] is None


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
        candidate_observations_repository=spy_repo,
        indicator_registry=FakeATRRegistry(),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
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
            candidate_observations_repository=spy_repo,
            indicator_registry=registry,
        )

        response = use_case.execute(
            AccumulationScreenRequest(
                tickers=["BBCA"],
                window_days=7,
                min_net_buy_days=1,
                as_of_date=as_of,
            )
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
        candidate_observations_repository=spy_repo_a,
        indicator_registry=FakeATRRegistry(),
    )
    response_a = use_case_a.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    spy_repo_b = SpyCandidateObservationsRepository()
    use_case_b = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(_fresh_summaries()),
        market_repository=MockMarketRepository(_fresh_candles()),
        candidate_observations_repository=spy_repo_b,
        indicator_registry=EmptyATRRegistry(),
    )
    response_b = use_case_b.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
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
