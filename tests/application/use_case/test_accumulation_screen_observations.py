"""Observation persistence/fingerprint behavior tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import (
    AccumulationScreenRequest,
)
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot
from tests.application.use_case.accumulation_screen_fixtures import (
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _make_use_case_with_all_providers,
    _summary,
    _weekdays,
)


def test_screen_persists_candidate_observations_when_repo_injected():
    """When candidate_observations_repository is injected, save_many receives
    correctly-shaped observations for each passing candidate."""
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
    assert obs.ticker == "BBCA"
    assert obs.snapshot_date == as_of

    payload = obs.payload
    assert payload["schema_version"] == 1
    assert payload["artifact_type"] == "candidate_observation"
    assert payload["ticker"] == "BBCA"
    assert payload["screen_result"] == "pass"
    fingerprint = payload["sub_signal_fingerprint"]
    assert fingerprint["rsi_at_signal"] is not None
    assert fingerprint["cnfb_20d_at_signal"] is not None
    assert fingerprint["coverage_score"] == 0.5
    assert fingerprint["conviction_score"] is not None
    assert fingerprint["coverage_score"] != fingerprint["conviction_score"]
    assert fingerprint["setup_phase_current"] is not None
    assert fingerprint["phase_coverage_score"] is not None
    assert fingerprint["phase_conviction_score"] is not None
    assert fingerprint["tp_market_cap_bucket"] == "UNKNOWN"
    assert "phase_history" in fingerprint
    assert "flow_evidence" in (payload.get("signal") or {})
    assert "setup_name" in fingerprint
    assert fingerprint["setup_name"] is None
    assert fingerprint["market_regime_at_signal"] is None
    assert fingerprint["regime_confidence_at_signal"] is None
    assert fingerprint["regime_stability_at_signal"] is None
    assert fingerprint["days_in_regime_at_signal"] is None
    assert fingerprint["regime_transition_warning_at_signal"] is None
    assert fingerprint["regime_detection_method_at_signal"] is None


def test_screen_persists_regime_attribution_fingerprint_when_market_context_supplied():
    """When a market_context is supplied on the request, the persisted
    sub_signal_fingerprint carries the full regime attribution: confidence,
    stability, days-in-regime, and market_regime_at_signal sourced from the
    MarketContext (rather than from decision_constraints)."""
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
    )

    market_context = MarketContext(
        regime=MarketRegime.RISK_ON,
        conviction=0.6,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=as_of,
        regime_confidence=0.8,
        regime_stability="STABLE",
        days_in_regime=6,
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            market_context=market_context,
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]
    assert fingerprint["market_regime_at_signal"] == MarketRegime.RISK_ON.value
    assert fingerprint["regime_confidence_at_signal"] == 0.8
    assert fingerprint["regime_stability_at_signal"] == "STABLE"
    assert fingerprint["days_in_regime_at_signal"] == 6
    assert fingerprint["regime_transition_warning_at_signal"] is None
    assert fingerprint["regime_detection_method_at_signal"] is None


def test_market_context_never_leaks_into_scoring_only_into_fingerprint_attribution():
    """Regression guard: market_context is observation-attribution only. Running
    the exact same screen twice — once with market_context=None and once with a
    real MarketContext supplied — must produce an IDENTICAL signal_assessment
    (score/strength/entry_quality) and IDENTICAL trade_setup for the same
    candidate. Only the regime-attribution keys inside sub_signal_fingerprint
    may differ between the two persisted observations."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]

    def _fresh_candles():
        return [
            _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100"))
            for i in range(45)
        ]

    def _fresh_summaries():
        return [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    # Run 1: no market_context.
    spy_repo_a = SpyCandidateObservationsRepository()
    use_case_a = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(_fresh_summaries()),
        market_repository=MockMarketRepository(_fresh_candles()),
        candidate_observations_repository=spy_repo_a,
    )
    response_a = use_case_a.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            market_context=None,
        )
    )

    # Run 2: fresh use-case instance, identical fixture data, but with a real
    # MarketContext supplied.
    spy_repo_b = SpyCandidateObservationsRepository()
    use_case_b = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(_fresh_summaries()),
        market_repository=MockMarketRepository(_fresh_candles()),
        candidate_observations_repository=spy_repo_b,
    )
    market_context = MarketContext(
        regime=MarketRegime.RISK_OFF,
        conviction=0.35,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=True,
        as_of_date=as_of,
        regime_confidence=0.9,
        regime_stability="TRANSITIONING",
        days_in_regime=2,
        transition_warning="regime shifted 2 days ago",
    )
    response_b = use_case_b.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            market_context=market_context,
        )
    )

    assert len(response_a.candidates) == 1
    assert len(response_b.candidates) == 1
    candidate_a = response_a.candidates[0]
    candidate_b = response_b.candidates[0]

    # Scoring/verdict must be bit-for-bit identical regardless of market_context.
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
    assert candidate_a.trade_setup is None
    assert candidate_b.trade_setup is None

    assert len(spy_repo_a.saved) == 1
    assert len(spy_repo_b.saved) == 1
    obs_a = spy_repo_a.saved[0]
    obs_b = spy_repo_b.saved[0]
    assert isinstance(obs_a, CandidateObservation)
    assert isinstance(obs_b, CandidateObservation)

    fingerprint_a = dict(obs_a.payload["sub_signal_fingerprint"])
    fingerprint_b = dict(obs_b.payload["sub_signal_fingerprint"])

    regime_attribution_keys = {
        "market_regime_at_signal",
        "regime_confidence_at_signal",
        "regime_stability_at_signal",
        "days_in_regime_at_signal",
        "regime_transition_warning_at_signal",
    }

    # These must differ — proof the attribution was actually threaded through.
    for key in regime_attribution_keys:
        assert fingerprint_a[key] != fingerprint_b[key], (
            f"expected {key} to differ between runs, both were {fingerprint_a[key]!r}"
        )
    assert fingerprint_b["market_regime_at_signal"] == MarketRegime.RISK_OFF.value
    assert fingerprint_b["regime_confidence_at_signal"] == 0.9
    assert fingerprint_b["regime_stability_at_signal"] == "TRANSITIONING"
    assert fingerprint_b["days_in_regime_at_signal"] == 2
    assert fingerprint_b["regime_transition_warning_at_signal"] == "regime shifted 2 days ago"

    # Everything else in the fingerprint must be identical — market_context must
    # not leak into any other sub-signal value.
    for key in regime_attribution_keys:
        fingerprint_a.pop(key)
        fingerprint_b.pop(key)
    assert fingerprint_a == fingerprint_b

    # Full candidate/signal payload equality (minus captured_at/timestamps)
    candidate_dict_a = obs_a.payload["candidate"]
    candidate_dict_b = obs_b.payload["candidate"]
    assert candidate_dict_a == candidate_dict_b
    assert obs_a.payload["trade_setup"] == obs_b.payload["trade_setup"]


def test_screen_persists_setup_family_fingerprint_when_swing_setup_catalog_matches():
    """When a swing_setup_catalog is injected and the screened candidate's
    derived signals MATCH a named setup (coiled-spring, family "breakout"),
    the persisted sub_signal_fingerprint carries the resolved setup-family
    fields end-to-end (screen -> PrimarySetupFamilyResolver -> payload)."""
    from src.application.use_case.evaluate_swing_setup_use_case import (
        CoiledSpringSetupConfig,
        ForeignBounceSetupConfig,
        PullbackContinuationSetupConfig,
        SmartMoneyConfirmedSetupConfig,
        SwingSetupCatalogConfig,
    )

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    # 130 days of varied-close candles so bb_width_pctile is not None
    candles = [
        _candle("BBCA", date(2025, 9, 1) + timedelta(days=i), Decimal("100") + Decimal(i % 5))
        for i in range(130)
    ]
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
    assert "matched_setup_families" in fingerprint
    assert "primary_setup_family" in fingerprint
    assert "setup_family_source" in fingerprint
    assert "setup_family_rationale" in fingerprint
    assert fingerprint["primary_setup_family"] == "breakout"
    assert "breakout" in fingerprint["matched_setup_families"]


def test_screen_persists_market_cap_bucket_when_fundamentals_available():
    spy_repo = SpyCandidateObservationsRepository()
    use_case, as_of, *_ = _make_use_case_with_all_providers(
        market_cap_idr=15_000_000_000_000,
        piotroski_score=8,
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
    assert fingerprint["tp_market_cap_bucket"] == "large"


def test_screen_result_returned_even_when_persistence_fails():
    """save_many failure must not block the screen response (best-effort persistence)."""
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    spy_repo.raise_on_save = RuntimeError("DB write failed")

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
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
    assert response.candidates[0].ticker == "BBCA"


def test_screen_populates_setup_phase_for_displayed_candidates():
    """Displayed screen candidates get setup_phase populated, not only persisted
    observations — no candidate_observations_repository is injected here."""
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        )
    )

    candidate = response.candidates[0]
    assert candidate.setup_phase is not None
    assert isinstance(candidate.setup_phase, SetupPhaseSnapshot)
    assert candidate.to_dict()["setup_phase"] == candidate.setup_phase.to_dict()


def test_screen_setup_phase_is_none_when_detection_fails(monkeypatch):
    """A detection failure must not crash the screen; setup_phase falls back to None."""
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    def _boom(self, **kwargs):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(
        "src.application.services.setup_phase_detector.SetupPhaseDetector.detect",
        _boom,
    )

    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
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
    assert response.candidates[0].setup_phase is None
    assert response.candidates[0].to_dict()["setup_phase"] is None


def test_screen_recomputes_setup_phase_when_stage2_family_differs_from_preliminary():
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResult,
    )

    class _FakeResolver:
        def resolve(self, *, candidate, strategy_evidence=None, **kwargs):
            if strategy_evidence is None:
                return PrimarySetupFamilyResult(
                    matched_setup_families=("breakout",),
                    primary_setup_family="breakout",
                    setup_family_source="detected_screen_evidence",
                )
            return PrimarySetupFamilyResult(
                matched_setup_families=("foreign_bounce", "breakout"),
                primary_setup_family="foreign_bounce",
                setup_family_source="strategy_evidence",
            )

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 9, 1) + timedelta(days=i), Decimal("100") + Decimal(i % 6))
        for i in range(130)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    spy_repo = SpyCandidateObservationsRepository()
    use_case = AccumulationScreenUseCase(
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        candidate_observations_repository=spy_repo,
        primary_setup_family_resolver=_FakeResolver(),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
            strategy_name="nonexistent-strategy-for-regression-test",
        )
    )

    assert len(response.candidates) == 1
    assert len(spy_repo.saved) == 1

    obs = spy_repo.saved[0]
    assert isinstance(obs, CandidateObservation)
    fingerprint = obs.payload["sub_signal_fingerprint"]

    assert fingerprint["primary_setup_family"] == "foreign_bounce"
    assert fingerprint["setup_family_source"] == "strategy_evidence"
    assert fingerprint["setup_phase_current"] == "COMPRESSION"
    assert fingerprint["phase_sequence_valid"] is False
