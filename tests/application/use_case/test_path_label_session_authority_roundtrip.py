"""Vertical slice: snapshot-bound path labels ↔ readiness (stable identity)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.services.accumulation_producer_readiness import (
    ProducerReadinessStatus,
    count_labels_by_horizon,
)
from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2,
)
from src.application.use_case.database_learning_lifecycle_use_case import (
    GenerateAccumulationPricePathLabelsUseCase,
    GenerateLearningLabelsRequest,
)
from src.application.use_case.get_accumulation_producer_readiness_use_case import (
    GetAccumulationProducerReadinessUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS_V2,
    AccumPopulationBinding,
    AssessmentPurpose,
    LabelAvailability,
    LearningContractError,
    LearningContractId,
    LearningObservation,
    OutcomeBasis,
    ProductionPolicySnapshot,
    recompute_path_label_fingerprint,
    stamp_universe_membership_id,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    PATH_LABEL_METRICS_SCHEMA_VERSION,
    STOCKBIT_TRADING_SESSIONS_CONTRACT,
    TradingSessionCalendarSnapshot,
    label_window_digest,
)
from src.infrastructure.data_providers.stockbit_trading_session_calendar_source import (
    StockbitTradingSessionCalendarSource,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_trading_session_calendar_snapshot_repository import (
    SQLiteTradingSessionCalendarSnapshotReadRepository,
    SQLiteTradingSessionCalendarSnapshotRepository,
)

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


def _snapshot(
    sessions: tuple[date, ...],
    *,
    start: date,
    end: date,
    revision: str = "stockbit.test.v1",
) -> TradingSessionCalendarSnapshot:
    return TradingSessionCalendarSnapshot.create(
        coverage_start=start,
        coverage_end=end,
        ordered_sessions=sessions,
        source_revision=revision,
        captured_at=NOW,
    )


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
        self._by: dict[str, list[Candle]] = {}
        for c in candles:
            self._by.setdefault(c.ticker, []).append(c)

    def get_candles(self, ticker, start_date=None, end_date=None):
        rows = []
        for c in self._by.get(ticker, []):
            if start_date is not None and c.date < start_date:
                continue
            if end_date is not None and c.date > end_date:
                continue
            rows.append(c)
        return sorted(rows, key=lambda x: x.date)


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


def test_producer_with_snapshot_passes_readiness_loading_exact_snapshot(tmp_path: Path) -> None:
    learn_db = tmp_path / "learn.db"
    repo = SQLiteLearningArtifactRepository(learn_db)
    o1 = _observation(day=1, ticker="BBCA")
    o2 = _observation(day=2, ticker="BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
    _seed_snapshots(repo)

    sessions = _weekdays(date(2026, 7, 1), date(2026, 8, 31))
    # Wide snapshot (simulates large attested history); identity is snapshot-bound.
    snap = _snapshot(sessions, start=date(2026, 6, 1), end=date(2026, 9, 30))
    cal_store = SQLiteTradingSessionCalendarSnapshotRepository(learn_db)
    cal_store.add_snapshot(snap)

    candles = [_candle("BBCA", s) for s in sessions] + [_candle("BBRI", s) for s in sessions]
    gen = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
        market_data=_Market(candles),
        corporate_actions=_CA(),
        session_snapshot=snap,
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
    labels = list(repo.list_labels([o1.observation_id, o2.observation_id]))
    assert all(lb.metrics["calendar_snapshot_id"] == snap.snapshot_id for lb in labels)

    # Growing the "cache" does not change snapshot identity loaded by status path.
    wider = _snapshot(
        _weekdays(date(2026, 6, 1), date(2026, 10, 31)),
        start=date(2026, 6, 1),
        end=date(2026, 10, 31),
        revision="stockbit.test.v1-later",
    )
    cal_store.add_snapshot(wider)

    read_repo = SQLiteTradingSessionCalendarSnapshotReadRepository(learn_db)
    report = GetAccumulationProducerReadinessUseCase(
        observations=repo,
        labels=repo,
        policy_snapshots=repo,
        session_snapshot_lookup=read_repo.get_snapshot,
    ).execute()
    assert report.cohort_count == 1
    assert report.cohorts[0].producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY
    # Labels still point at original snapshot, not the later wider one.
    assert all(lb.metrics["calendar_snapshot_id"] == snap.snapshot_id for lb in labels)


def test_growing_cache_does_not_invalidate_label_window_digest() -> None:
    sessions = _weekdays(date(2026, 7, 1), date(2026, 8, 15))
    snap = _snapshot(sessions, start=date(2026, 7, 1), end=date(2026, 8, 15))
    signal = date(2026, 7, 1)
    first10 = snap.first_n_sessions_after(signal, 10)
    assert first10 is not None
    d1 = label_window_digest(
        calendar_snapshot_id=snap.snapshot_id,
        label_contract_id=LearningContractId.ACCUM_10D_LABEL.value,
        signal_date=signal,
        sessions=first10,
    )
    # A wider snapshot has a different snapshot_id; old label digest stays valid for old id.
    wider = _snapshot(
        _weekdays(date(2026, 7, 1), date(2026, 12, 31)),
        start=date(2026, 7, 1),
        end=date(2026, 12, 31),
    )
    assert wider.snapshot_id != snap.snapshot_id
    d2 = label_window_digest(
        calendar_snapshot_id=snap.snapshot_id,
        label_contract_id=LearningContractId.ACCUM_10D_LABEL.value,
        signal_date=signal,
        sessions=first10,
    )
    assert d1 == d2


def test_mutated_revision_or_snapshot_id_blocks_readiness() -> None:
    from dataclasses import replace

    from src.domain.value_objects.learning_artifacts import (
        LearningOutcomeLabel,
        _artifact_payload,
        artifact_digest,
    )

    sessions = _weekdays(date(2026, 7, 1), date(2026, 8, 31))
    snap = _snapshot(sessions, start=date(2026, 7, 1), end=date(2026, 8, 31))
    obs = [_observation(day=1), _observation(day=2, ticker="BBRI")]
    first10 = snap.first_n_sessions_after(date(2026, 7, 1), 10)
    assert first10 is not None
    metrics = {
        "ticker": "BBCA",
        "signal_date": "2026-07-01",
        "label_window_start": first10[0].isoformat(),
        "label_window_end": first10[-1].isoformat(),
        "label_window_sessions": [s.isoformat() for s in first10],
        "calendar_snapshot_id": snap.snapshot_id,
        "calendar_contract_id": STOCKBIT_TRADING_SESSIONS_CONTRACT,
        "calendar_source_revision": snap.source_revision,
        "label_window_digest": label_window_digest(
            calendar_snapshot_id=snap.snapshot_id,
            label_contract_id=LearningContractId.ACCUM_10D_LABEL.value,
            signal_date=date(2026, 7, 1),
            sessions=first10,
        ),
        "path_label_metrics_schema_version": PATH_LABEL_METRICS_SCHEMA_VERSION,
        "entry_reference_price": 100.0,
        "close_return_pct": 3.5,
        "max_forward_return_pct": 5.0,
        "max_adverse_excursion_pct": -1.0,
        "days_to_peak": 2,
        "days_to_trough": 1,
    }
    good = LearningOutcomeLabel.create(
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

    def lookup(sid: str):
        return snap if sid == snap.snapshot_id else None

    ok = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[good],
        observations_by_id={o.observation_id: o for o in obs},
        session_snapshot_lookup=lookup,
    )
    assert ok.counts_by_horizon["H10"].available == 1

    invented = replace(
        good,
        metrics={**dict(good.metrics), "calendar_source_revision": "invented"},
    )
    invented = replace(
        invented,
        artifact_digest=artifact_digest(
            _artifact_payload(invented, id_field="label_id", digest_field="artifact_digest")
        ),
    )
    bad = count_labels_by_horizon(
        observation_ids=[o.observation_id for o in obs],
        labels=[invented],
        observations_by_id={o.observation_id: o for o in obs},
        session_snapshot_lookup=lookup,
    )
    assert bad.counts_by_horizon["H10"].available == 0
    assert any("calendar_source_revision_mismatch" in r for r in bad.invalid_reasons)


def test_missing_ticker_candle_writes_no_terminal_label(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "l.db")
    obs = _observation(day=1)
    repo.add_observation(obs)
    sessions = _weekdays(date(2026, 7, 1), date(2026, 8, 31))
    snap = _snapshot(sessions, start=date(2026, 7, 1), end=date(2026, 8, 31))
    expected = snap.first_n_sessions_after(date(2026, 7, 1), 10)
    assert expected is not None
    candles = [_candle("BBCA", s) for s in expected if s != expected[4]]
    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
        market_data=_Market(candles),
        corporate_actions=_CA(),
        session_snapshot=snap,
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


def test_strict_stockbit_source_rejects_missing_result_and_network() -> None:
    class _Client:
        def __init__(self, pages):
            self.pages = list(pages)

        def get(self, url):
            if not self.pages:
                raise RuntimeError("network down")
            return self.pages.pop(0)

    # Single-page weekday success (not multi-page)
    page1 = {
        "data": {
            "result": [
                {"date": "2026-07-01"},
                {"date": "2026-07-02"},
                {"date": "2026-07-03"},
            ]
        }
    }
    src = StockbitTradingSessionCalendarSource(
        _Client([page1]),
        source_revision="rev-a",
        captured_at=NOW,
    )
    snap = src.fetch_snapshot(date(2026, 7, 1), date(2026, 7, 10))
    assert snap.contract_id == STOCKBIT_TRADING_SESSIONS_CONTRACT

    # Network failure
    with pytest.raises(LearningContractError):
        StockbitTradingSessionCalendarSource(_Client([]), captured_at=NOW).fetch_snapshot(
            date(2026, 7, 1), date(2026, 7, 10)
        )

    # Missing data.result is malformed (not empty success)
    with pytest.raises(LearningContractError, match="missing data.result"):
        StockbitTradingSessionCalendarSource(
            _Client([{"data": {}}]), captured_at=NOW
        ).fetch_snapshot(date(2026, 7, 1), date(2026, 7, 2))


def test_status_read_only_snapshot_repo_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    repo = SQLiteTradingSessionCalendarSnapshotReadRepository(missing)
    assert repo.get_snapshot("x") is None
    assert not missing.exists()
    assert list(tmp_path.iterdir()) == []


def test_status_read_only_does_not_mutate_db(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    write = SQLiteTradingSessionCalendarSnapshotRepository(db)
    sessions = _weekdays(date(2026, 7, 1), date(2026, 7, 15))
    snap = _snapshot(sessions, start=date(2026, 7, 1), end=date(2026, 7, 15))
    write.add_snapshot(snap)
    before = db.stat()
    ro = SQLiteTradingSessionCalendarSnapshotReadRepository(db)
    assert ro.get_snapshot(snap.snapshot_id) is not None
    after = db.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
