"""Vertical slice: production path-label generator ↔ readiness (session authority)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from src.application.services.accumulation_producer_readiness import (
    ProducerReadinessStatus,
    count_labels_by_horizon,
    project_cohort_readiness,
)
from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2,
)
from src.application.use_case.database_learning_lifecycle_use_case import (
    GenerateAccumulationPricePathLabelsUseCase,
    GenerateLearningLabelsRequest,
)
from src.application.use_case.get_accumulation_producer_readiness_use_case import (
    coverage_from_available_labels,
)
from src.domain.entities.candle import Candle
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS_V2,
    AccumPopulationBinding,
    AssessmentPurpose,
    LabelAvailability,
    LearningContractId,
    LearningObservation,
    OutcomeBasis,
    ProductionPolicySnapshot,
    recompute_path_label_fingerprint,
    stamp_universe_membership_id,
)
from src.infrastructure.persistence.sqlite_ihsg_trading_session_calendar_read_repository import (
    SQLiteIHSGTradingSessionCalendarReadRepository,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_market_data_read_repository import (
    SQLiteMarketDataReadRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
COMPAT = "sha256:" + ("ab" * 32)
MEMBERSHIP = ["BBCA", "BBRI"]
NAMED = ["ASII", "BBCA", "BBRI", "BMRI", "TLKM"]
UNIVERSE = stamp_universe_membership_id(MEMBERSHIP)
MATERIAL = "sha256:" + ("11" * 32)


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return tuple(out)


def _candle(ticker: str, d: date, close: str = "100") -> Candle:
    return Candle(
        ticker=ticker,
        date=d,
        open=Decimal(close),
        high=Decimal(close) + Decimal("2"),
        low=Decimal(close) - Decimal("1"),
        close=Decimal(close),
        volume=1000,
    )


def _calendar(sessions: tuple[date, ...], *, start: date, end: date) -> KnownTradingSessionCalendar:
    return KnownTradingSessionCalendar(sessions=sessions, coverage_start=start, coverage_end=end)


def _observation(*, day: int, ticker: str = "BBCA") -> LearningObservation:
    sd = f"2026-07-{day:02d}"
    at = datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc)
    binding = AccumPopulationBinding.create(
        membership_tickers=MEMBERSHIP,
        named_universe_tickers=NAMED,
        membership_session=sd,
        pit_tradable_lookback_sessions=10,
        producer_source_revision="ai-saham@test",
    )
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=COMPAT,
        cutoff_at=at,
        universe_id=UNIVERSE,
        window_id=f"{ticker}:{sd}",
        decision_payload={
            "schema_version": 11,
            "artifact_type": "accumulation_session_observation",
            "ticker": ticker,
            "session_date": sd,
            "captured_at": at.isoformat(),
            "canonical_window": 7,
            "workflow": "research_accum_capture",
            "horizon_primary": "accum_10d",
            "shared": {
                "current_price": 100.0,
                "provenance": {
                    "decision_at": at.isoformat(),
                    "latest_completed_session": sd,
                    "analysis_as_of": sd,
                    "market_session_name": "regular",
                    "is_eod_pending": False,
                },
            },
            "features_by_window": {
                "7": {"trade_setup": {"action": "WATCH"}, "signal": {}, "candidate": {}},
                "30": {"trade_setup": {"action": "WATCH"}, "signal": {}, "candidate": {}},
                "90": {"trade_setup": {"action": "WATCH"}, "signal": {}, "candidate": {}},
            },
            "population_binding": binding.to_dict(),
        },
        captured_at=at,
    )


class _CA:
    def has_any_sync_marker(self) -> bool:
        return True

    def get_events_for_ticker(self, *args, **kwargs):
        return ()


class _Market:
    def __init__(self, candles: list[Candle]) -> None:
        self._by_ticker: dict[str, list[Candle]] = {}
        for c in candles:
            self._by_ticker.setdefault(c.ticker, []).append(c)

    def get_candles(self, ticker, start_date=None, end_date=None):
        rows = self._by_ticker.get(ticker, [])
        out = []
        for c in rows:
            if start_date is not None and c.date < start_date:
                continue
            if end_date is not None and c.date > end_date:
                continue
            out.append(c)
        return sorted(out, key=lambda x: x.date)


def _seed_snapshots(repo: SQLiteLearningArtifactRepository) -> None:
    for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS_V2:
        d = ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2[policy_id]
        repo.add_policy_snapshot(
            ProductionPolicySnapshot.create(
                contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
                producer_observation_contract="accumulation-discovery.v2",
                compatibility_id=COMPAT,
                policy_id=policy_id,
                policy_version=d.policy_version,
                decision_type=d.decision_type,
                semantic_engine_contract_id=d.semantic_engine_contract_id,
                material_config_hash=MATERIAL,
                canonical_payload={
                    "policy_id": policy_id,
                    "policy_version": d.policy_version,
                    "decision_type": d.decision_type,
                    "semantic_engine_contract_id": d.semantic_engine_contract_id,
                },
                source_revision="test",
                created_at=NOW,
            )
        )


def test_producer_h10_roundtrip_passes_readiness(tmp_path: Path) -> None:
    """production label generator → persist → readiness accepts AVAILABLE H10."""
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    o1 = _observation(day=1, ticker="BBCA")
    o2 = _observation(day=2, ticker="BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
    _seed_snapshots(repo)

    sessions = _weekdays(date(2026, 7, 1), date(2026, 8, 31))
    cal = _calendar(sessions, start=date(2026, 7, 1), end=date(2026, 8, 31))
    candles = [_candle("BBCA", s) for s in sessions] + [_candle("BBRI", s) for s in sessions]
    market = _Market(candles)

    gen = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
        market_data=market,
        corporate_actions=_CA(),
        session_calendar=cal,
    )
    result = gen.execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id=COMPAT,
            label_contract=LearningContractId.ACCUM_10D_LABEL,
            labeled_at=NOW,
        )
    )
    assert result.inserted_count == 2
    assert all(lb.availability is LabelAvailability.AVAILABLE for lb in result.labels)
    assert all("label_window_sessions" in lb.metrics for lb in result.labels)

    labels = repo.list_labels([o1.observation_id, o2.observation_id])
    cohort = project_cohort_readiness(
        compatibility_id=COMPAT,
        observations=[o1, o2],
        labels=labels,
        snapshots=repo.list_policy_snapshots(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY, compatibility_id=COMPAT
        ),
        purpose_value=AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
        session_calendar=cal,
    )
    assert cohort.labels_by_horizon["H10"].available == 2
    assert cohort.producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_missing_ticker_candle_on_market_session_writes_no_terminal_label(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "learn.db")
    obs = _observation(day=1)
    repo.add_observation(obs)
    sessions = _weekdays(date(2026, 7, 1), date(2026, 8, 31))
    cal = _calendar(sessions, start=date(2026, 7, 1), end=date(2026, 8, 31))
    expected = cal.first_n_sessions_after(date(2026, 7, 1), 10)
    assert expected is not None
    # Drop the 5th expected session candle.
    candles = [_candle("BBCA", s) for s in expected if s != expected[4]]
    market = _Market(candles)
    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
        market_data=market,
        corporate_actions=_CA(),
        session_calendar=cal,
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id=COMPAT,
            label_contract=LearningContractId.ACCUM_10D_LABEL,
            labeled_at=NOW,
        )
    )
    assert result.inserted_count == 0
    assert result.skipped_count == 1
    assert repo.list_labels([obs.observation_id]) == ()


def test_holiday_omitted_from_first_n_and_shifted_window_blocks() -> None:
    holiday = date(2026, 7, 2)
    sessions = tuple(s for s in _weekdays(date(2026, 7, 1), date(2026, 8, 31)) if s != holiday)
    cal = _calendar(sessions, start=date(2026, 7, 1), end=date(2026, 8, 31))
    signal = date(2026, 7, 1)
    honest = cal.first_n_sessions_after(signal, 10)
    assert honest is not None
    assert honest[0] == date(2026, 7, 3)

    obs = [_observation(day=1), _observation(day=3, ticker="BBRI")]
    # Build a shifted exact-length weekday window that is not first-N.
    from src.domain.services.trading_session_calendar import (
        IDX_TRADING_SESSIONS_CONTRACT,
        PATH_LABEL_METRICS_SCHEMA_VERSION,
        session_calendar_digest,
        session_calendar_revision,
    )

    shifted = tuple(s for s in sessions if s >= date(2026, 7, 20))[:10]
    metrics = {
        "ticker": "BBCA",
        "signal_date": signal.isoformat(),
        "label_window_start": shifted[0].isoformat(),
        "label_window_end": shifted[-1].isoformat(),
        "label_window_sessions": [s.isoformat() for s in shifted],
        "session_calendar_contract": IDX_TRADING_SESSIONS_CONTRACT,
        "session_calendar_revision": session_calendar_revision(cal),
        "session_calendar_digest": session_calendar_digest(cal),
        "path_label_metrics_schema_version": PATH_LABEL_METRICS_SCHEMA_VERSION,
        "entry_reference_price": 100.0,
        "close_return_pct": 3.5,
        "max_forward_return_pct": 5.0,
        "max_adverse_excursion_pct": -1.0,
        "days_to_peak": 2,
        "days_to_trough": 1,
    }
    from src.domain.value_objects.learning_artifacts import LearningOutcomeLabel

    bad = LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id=obs[0].observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="SUCCESS",
        metrics=metrics,
        fingerprint=recompute_path_label_fingerprint(
            observation_id=obs[0].observation_id,
            observation_artifact_digest=obs[0].artifact_digest,
            label_contract=LearningContractId.ACCUM_10D_LABEL,
        ),
        labeled_at=NOW,
    )
    counts = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[bad],
        observations_by_id={o.observation_id: o for o in obs},
        session_calendar=cal,
    )
    assert counts.counts_by_horizon["H10"].available == 0
    assert any("label_window_not_first_n" in r for r in counts.invalid_reasons)


def test_coverage_from_labels_not_newest_observation_plus_buffer() -> None:
    from src.domain.services.trading_session_calendar import (
        IDX_TRADING_SESSIONS_CONTRACT,
        PATH_LABEL_METRICS_SCHEMA_VERSION,
    )
    from src.domain.value_objects.learning_artifacts import LearningOutcomeLabel

    # Mature H10 from July; unlabeled newer obs must not expand coverage.
    o_old = _observation(day=1)
    metrics = {
        "ticker": "BBCA",
        "signal_date": "2026-07-01",
        "label_window_start": "2026-07-02",
        "label_window_end": "2026-07-15",
        "label_window_sessions": [
            (date(2026, 7, 2) + timedelta(days=i)).isoformat() for i in range(14)
        ][:10],
        "session_calendar_contract": IDX_TRADING_SESSIONS_CONTRACT,
        "session_calendar_revision": "x",
        "session_calendar_digest": "y",
        "path_label_metrics_schema_version": PATH_LABEL_METRICS_SCHEMA_VERSION,
        "entry_reference_price": 100.0,
        "close_return_pct": 1.0,
        "max_forward_return_pct": 1.0,
        "max_adverse_excursion_pct": -0.5,
        "days_to_peak": 1,
        "days_to_trough": 1,
    }
    # Fix sessions to exactly 10 weekdays starting Jul 2
    sessions = _weekdays(date(2026, 7, 2), date(2026, 7, 31))[:10]
    metrics["label_window_sessions"] = [s.isoformat() for s in sessions]
    metrics["label_window_start"] = sessions[0].isoformat()
    metrics["label_window_end"] = sessions[-1].isoformat()
    label = LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id=o_old.observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="SUCCESS",
        metrics=metrics,
        fingerprint=recompute_path_label_fingerprint(
            observation_id=o_old.observation_id,
            observation_artifact_digest=o_old.artifact_digest,
            label_contract=LearningContractId.ACCUM_10D_LABEL,
        ),
        labeled_at=NOW,
    )
    coverage = coverage_from_available_labels([label])
    assert coverage == (date(2026, 7, 1), sessions[-1])
    # No AVAILABLE labels → no coverage (COLLECTING, no future-day demand).
    assert coverage_from_available_labels([]) is None


def test_status_read_only_creates_nothing_on_missing_db(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.db"
    assert not missing.exists()
    try:
        SQLiteMarketDataReadRepository(missing).get_date_range("IHSG")
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass
    assert not missing.exists()
    cal = SQLiteIHSGTradingSessionCalendarReadRepository(missing).load_calendar(
        coverage_start=date(2026, 7, 1),
        coverage_end=date(2026, 7, 31),
    )
    assert cal is None
    assert not missing.exists()
    assert list(tmp_path.iterdir()) == []


def test_status_read_only_does_not_mutate_existing_db(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    write = SQLiteMarketRepository(db)
    write.save_candles([_candle("IHSG", date(2026, 7, 1)), _candle("IHSG", date(2026, 7, 2))])
    before_stat = db.stat()
    before_size = before_stat.st_size
    before_mtime = before_stat.st_mtime_ns
    before_count = len(write.get_candles("IHSG"))

    reader = SQLiteMarketDataReadRepository(db)
    assert reader.get_date_range("IHSG") is not None
    cal_repo = SQLiteIHSGTradingSessionCalendarReadRepository(db)
    cal = cal_repo.load_calendar(coverage_start=date(2026, 7, 1), coverage_end=date(2026, 7, 2))
    assert cal is not None
    assert len(cal.sessions) == 2

    after = db.stat()
    assert after.st_size == before_size
    assert after.st_mtime_ns == before_mtime
    assert len(write.get_candles("IHSG")) == before_count


def test_ihsg_read_repo_treats_weekday_gap_as_non_session(tmp_path: Path) -> None:
    """Holiday-like gap: Friday + Tuesday with Monday missing is still proven."""
    db = tmp_path / "m.db"
    write = SQLiteMarketRepository(db)
    write.save_candles(
        [
            _candle("IHSG", date(2026, 7, 17)),  # Fri
            # Mon 20 missing (holiday)
            _candle("IHSG", date(2026, 7, 21)),  # Tue
            _candle("IHSG", date(2026, 7, 22)),
        ]
    )
    # Span must be covered by min/max — add endpoints
    write.save_candles([_candle("IHSG", date(2026, 7, 23)), _candle("IHSG", date(2026, 7, 24))])
    cal = SQLiteIHSGTradingSessionCalendarReadRepository(db).load_calendar(
        coverage_start=date(2026, 7, 17),
        coverage_end=date(2026, 7, 24),
    )
    assert cal is not None
    assert date(2026, 7, 20) not in cal.sessions
    assert date(2026, 7, 17) in cal.sessions
    assert date(2026, 7, 21) in cal.sessions


def test_membership_subset_enforced_on_binding() -> None:
    from src.domain.value_objects.learning_artifacts import LearningContractError

    try:
        AccumPopulationBinding.create(
            membership_tickers=["ASII", "FAKE"],
            named_universe_tickers=["ASII"],
            membership_session="2026-07-01",
            pit_tradable_lookback_sessions=10,
            producer_source_revision="x",
        )
        raise AssertionError("expected subset rejection")
    except LearningContractError as exc:
        assert "subset" in str(exc)
