"""Vertical: sync snapshot → labels → readiness (stable snapshot binding)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from src.application.services.accumulation_producer_readiness import ProducerReadinessStatus
from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2,
)
from src.application.services.trading_session_calendar_selection import (
    select_calendar_snapshot,
)
from src.application.use_case.database_learning_lifecycle_use_case import (
    GenerateAccumulationPricePathLabelsUseCase,
    GenerateLearningLabelsRequest,
)
from src.application.use_case.get_accumulation_producer_readiness_use_case import (
    GetAccumulationProducerReadinessUseCase,
)
from src.application.use_case.sync_trading_session_calendar_snapshot_use_case import (
    SyncTradingSessionCalendarRequest,
    SyncTradingSessionCalendarSnapshotUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.trading_session_calendar_repository import (
    TradingSessionCalendarSnapshotReadError,
)
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS_V2,
    AccumPopulationBinding,
    AssessmentPurpose,
    LearningContractId,
    LearningObservation,
    ProductionPolicySnapshot,
    stamp_universe_membership_id,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
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
COMPAT = "sha256:" + ("cd" * 32)
MEMBERSHIP = ["BBCA", "BBRI"]
NAMED = ["ASII", "BBCA", "BBRI", "BMRI", "TLKM"]
UNIVERSE = stamp_universe_membership_id(MEMBERSHIP)
MATERIAL = "sha256:" + ("22" * 32)


def _weekdays(start: date, end: date) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _candle(ticker: str, d: date) -> Candle:
    return Candle(
        ticker=ticker,
        date=d,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=1000,
    )


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


class _CA:
    def has_any_sync_marker(self) -> bool:
        return True

    def get_events_for_ticker(self, *args, **kwargs):
        return ()


class _ScriptedClient:
    def __init__(self, dates: list[str]):
        self.dates = dates

    def get(self, url: str):
        return {"data": {"result": [{"date": d} for d in self.dates]}}


def _observation(*, day: int, ticker: str = "BBCA") -> LearningObservation:
    sd = f"2026-07-{day:02d}"
    at = datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc)
    binding = AccumPopulationBinding.create(
        membership_tickers=MEMBERSHIP,
        named_universe_tickers=NAMED,
        membership_session=sd,
        pit_tradable_lookback_sessions=10,
        producer_source_revision="test",
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
            "schema_version": 12,
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


def _seed_policy(repo: SQLiteLearningArtifactRepository) -> None:
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


def test_sync_labels_readiness_vertical(tmp_path: Path) -> None:
    db = tmp_path / "learn.db"
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(day=1, ticker="BBCA")
    o2 = _observation(day=2, ticker="BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
    _seed_policy(repo)

    dates = _weekdays(date(2026, 7, 1), date(2026, 8, 31))
    source = StockbitTradingSessionCalendarSource(
        _ScriptedClient(dates),
        captured_at=NOW,
        source_revision="stockbit.vertical.v1",
    )
    snap_write = SQLiteTradingSessionCalendarSnapshotRepository(db)
    sync = SyncTradingSessionCalendarSnapshotUseCase(source=source, snapshots=snap_write)
    result = sync.execute(
        SyncTradingSessionCalendarRequest(
            coverage_start=date(2026, 7, 1),
            coverage_end=date(2026, 8, 31),
        )
    )
    assert result.inserted is True
    assert result.session_count == len(dates)
    snap = snap_write.get_snapshot(result.snapshot_id)
    assert snap is not None

    # Selection independent of insertion order (single eligible here).
    assert select_calendar_snapshot((snap,), signal_date=date(2026, 7, 1), horizon_days=10) is snap

    sessions = tuple(date.fromisoformat(d) for d in dates)
    candles = [_candle("BBCA", s) for s in sessions] + [_candle("BBRI", s) for s in sessions]
    gen = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
        market_data=_Market(candles),
        corporate_actions=_CA(),
        session_snapshot=snap,
    )
    labeled = gen.execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id=COMPAT,
            label_contract=LearningContractId.ACCUM_10D_LABEL,
            labeled_at=NOW,
        )
    )
    assert labeled.inserted_count == 2
    labels = repo.list_labels([o1.observation_id, o2.observation_id])
    assert all(lb.metrics["calendar_snapshot_id"] == snap.snapshot_id for lb in labels)

    # Newer wider snapshot does not invalidate old labels.
    later = TradingSessionCalendarSnapshot.create(
        coverage_start=date(2026, 6, 1),
        coverage_end=date(2026, 10, 31),
        ordered_sessions=tuple(
            date.fromisoformat(d) for d in _weekdays(date(2026, 6, 1), date(2026, 10, 31))
        ),
        source_revision="stockbit.vertical.v2",
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    snap_write.add_snapshot(later)

    ro = SQLiteTradingSessionCalendarSnapshotReadRepository(db)
    before = db.stat()
    report = GetAccumulationProducerReadinessUseCase(
        observations=repo,
        labels=repo,
        policy_snapshots=repo,
        session_snapshot_lookup=ro.get_snapshot,
    ).execute()
    after = db.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
    assert report.cohorts[0].producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_corrupt_snapshot_json_blocks_not_crashes(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    write = SQLiteTradingSessionCalendarSnapshotRepository(db)
    sessions = tuple(date.fromisoformat(d) for d in _weekdays(date(2026, 7, 1), date(2026, 7, 15)))
    snap = TradingSessionCalendarSnapshot.create(
        coverage_start=date(2026, 7, 1),
        coverage_end=date(2026, 7, 15),
        ordered_sessions=sessions,
        source_revision="r",
        captured_at=NOW,
    )
    write.add_snapshot(snap)
    # Corrupt artifact_json while leaving PK
    import sqlite3

    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "UPDATE trading_session_calendar_snapshots SET artifact_json = ? WHERE snapshot_id = ?",
            ("{not-json", snap.snapshot_id),
        )
        conn.commit()
    ro = SQLiteTradingSessionCalendarSnapshotReadRepository(db)
    try:
        ro.get_snapshot(snap.snapshot_id)
        raise AssertionError("expected read error")
    except TradingSessionCalendarSnapshotReadError:
        pass
