"""Phase 2: pre-open saved observations (ADR-048)."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from src.application.services.pre_open_observation_payload import (
    PRE_OPEN_OBSERVATION_CONTRACT,
    PRE_OPEN_WORKFLOW,
    derive_pre_open_screen_result,
)
from src.application.services.pre_open_observation_persister import (
    PreOpenObservationPersister,
)
from src.application.services.pre_open_ops_day_export import (
    write_pre_open_ops_day_export,
)
from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
)
from src.application.use_case import opening_grade_use_case as opening_grade
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenDataFreshness,
    PreOpenRiskSummary,
    PreOpenSignalSummary,
    PreOpenWorkflowRequest,
    PreOpenWorkflowResponse,
)
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
from src.domain.value_objects.screener_result import PreOpenScreenResult, ScreenerCandidate
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)


def _candidate(ticker: str = "BBCA") -> ScreenerCandidate:
    return ScreenerCandidate(
        ticker=ticker,
        iev=200_000,
        entry_price=Decimal("10050"),
        stop_loss_price=Decimal("9800"),
        capital=Decimal("3000000"),
        trend_signal="BULLISH",
        prev_close=Decimal("10000"),
        gap_pct=Decimal("1.0"),
        iep=10100,
        iep_gap_pct=Decimal("1.0"),
        best_bid=Decimal("10050"),
        bid_gap_pct=Decimal("0.5"),
        gap_price_source="IEP",
        entry_range_low=Decimal("9900"),
        entry_range_high=Decimal("10100"),
        bid_offer_imbalance=0.6,
        spread_pct=Decimal("0.4"),
    )


def _signal_summary(
    *,
    score: int = 80,
    entry_quality: str = "ENTER",
) -> PreOpenSignalSummary:
    return PreOpenSignalSummary(
        contract="pre_open_directional_baseline.v1",
        direction="BULLISH",
        confidence="HIGH",
        auction_quality="RELIABLE",
        raw_score=score,
        score=score,
        strength="STRONG",
        entry_quality=entry_quality,
        factors={
            "iep_direction": "UP",
            "book_pressure_state": "BUY",
            "participation_state": "BUILDING",
            "iep_gap_pct": 1.0,
            "book_pressure": 0.6,
            "delta_iev": 20_000,
            "delta_iev_ratio": 0.1,
            "iev_intensity": 2.0,
            "spread_pct": 0.4,
            "rsi_extension": False,
            "unusual_volume": False,
        },
        rationale=("direction:agreement_bullish",),
        quality_reasons=(),
        signal_authority_coverage=1.0,
    )


def test_pre_open_observation_contract_is_v3():
    assert PRE_OPEN_OBSERVATION_CONTRACT == "pre-open-open-30m.v3"


def test_derive_screen_result_funnel():
    assert (
        derive_pre_open_screen_result(has_entry_range=False, signal_summary=None, trade_setup=None)
        == "rejected_plan"
    )
    assert (
        derive_pre_open_screen_result(has_entry_range=True, signal_summary=None, trade_setup=None)
        == "rejected_auction_missing"
    )
    sig = _signal_summary(entry_quality="AVOID")
    assert (
        derive_pre_open_screen_result(has_entry_range=True, signal_summary=sig, trade_setup=None)
        == "rejected_signal"
    )
    sig_ok = _signal_summary()
    assert (
        derive_pre_open_screen_result(has_entry_range=True, signal_summary=sig_ok, trade_setup=None)
        == "pass"
    )


def test_persist_observations_and_identity_upsert(tmp_path: Path, monkeypatch):
    db = tmp_path / "obs.db"
    repo = SQLiteCandidateObservationsRepository(db)
    persister = PreOpenObservationPersister(repo, PreOpenDirectionalBaselineConfig())

    run_date = date(2026, 6, 18)
    cand = _candidate()
    sig = _signal_summary(score=72)
    risk = PreOpenRiskSummary(
        risk_level_name="LOW_RISK",
        gate_triggered=None,
        gate_is_structural=None,
        confidence=90,
    )
    setup = TradeSetup(
        ticker="BBCA",
        snapshot_date=run_date,
        action=SetupAction.ENTER,
        signal_score=72,
        signal_score_raw=72,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="test",
    )
    response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=run_date,
            iev_min=100_000,
            total_movers_seen=1,
            candidates=[cand],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=run_date, candle_end=None, broker_end=None
        ),
        risk_by_ticker={"BBCA": risk},
        signal_by_ticker={"BBCA": sig},
        trade_setup_by_ticker={"BBCA": setup},
        source_status=PreOpenSourceStatus.LIVE_SUCCESS,
        source_snapshot_ref=None,
        source_is_live=True,
        capture_phase="NCP_LOCKED",
        collection_started_at=datetime(2026, 6, 18, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta")),
        decision_at=datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
        decision_snapshot_ref="test:ncp",
    )
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(iev_min=100_000, top_n=5, fast_mode=True),
        run_date=run_date,
    )

    n1 = persister.persist(
        response,
        request,
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
    )
    assert n1 == 1

    rows = repo.list_canonical_by_date(run_date)
    pre_open_rows = [r for r in rows if r.workflow == PRE_OPEN_WORKFLOW]
    assert len(pre_open_rows) == 1
    row = pre_open_rows[0]
    assert row.observation_contract == PRE_OPEN_OBSERVATION_CONTRACT
    assert row.payload["signal"]["score"] == 72
    assert row.payload["signal"]["contract"] == "pre_open_directional_baseline.v1"
    assert row.payload["signal"]["direction"] == "BULLISH"
    assert row.payload["signal"]["confidence"] == "HIGH"
    assert row.payload["signal"]["auction_quality"] == "RELIABLE"
    assert row.payload["signal"]["factors"]["delta_iev"] == 20_000
    assert row.payload["signal"]["rationale"] == ["direction:agreement_bullish"]
    assert row.payload["trade_setup"]["action"] == "ENTER"
    assert row.payload["screen_result"] == "pass"
    assert row.payload["candidate"]["iep"] == 10100
    assert row.payload["candidate"]["iep_gap_pct"] == "1.0"
    assert row.payload["candidate"]["best_bid"] == "10050"
    assert row.payload["candidate"]["bid_gap_pct"] == "0.5"
    assert row.payload["candidate"]["gap_price_source"] == "IEP"
    assert row.decision_at is not None
    assert row.decision_at.hour == 8 and row.decision_at.minute == 57

    ops_path = write_pre_open_ops_day_export(response, tmp_path / "opening")
    ops_payload = json.loads(ops_path.read_text())
    ops_candidate = ops_payload["candidates"][0]
    assert ops_candidate["iep"] == 10100
    assert ops_candidate["iep_gap_pct"] == 1.0
    assert ops_candidate["best_bid"] == 10050.0
    assert ops_candidate["bid_gap_pct"] == 0.5
    assert ops_candidate["gap_price_source"] == "IEP"

    grade_root = tmp_path / "grade"
    grade_day = grade_root / "20260618"
    grade_day.mkdir(parents=True)
    (grade_day / "track_0900.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-18T09:00:01+07:00",
                "tickers": {
                    "BBCA": {
                        "opening_price": 10000,
                        "opening_price_confidence": "HIGH",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(opening_grade, "OPENING_DATA_DIR", grade_root)
    grade = opening_grade.compute_grade(
        run_date,
        observations_repository=repo,
    )
    assert grade["per_ticker"][0]["iep"] == 10100.0
    assert grade["per_ticker"][0]["iep_error_pct"] == 1.0
    assert grade["iep_accuracy"]["mean_error_pct"] == 1.0

    # Same identity upsert replaces, does not duplicate
    n2 = persister.persist(
        response,
        request,
        captured_at=datetime(2026, 6, 18, 8, 58, tzinfo=ZoneInfo("Asia/Jakarta")),
    )
    assert n2 == 1
    rows2 = [r for r in repo.list_canonical_by_date(run_date) if r.workflow == PRE_OPEN_WORKFLOW]
    assert len(rows2) == 1
    # Capture identity: score still from payload write (same content)
    assert rows2[0].payload["signal"]["score"] == 72


def test_persist_noop_without_repository():
    persister = PreOpenObservationPersister(None)
    run_date = date(2026, 6, 18)
    response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=run_date,
            iev_min=100_000,
            total_movers_seen=0,
            candidates=[],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=run_date, candle_end=None, broker_end=None
        ),
    )
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(fast_mode=True),
        run_date=run_date,
    )
    assert persister.persist(response, request) == 0


def test_persist_includes_hard_filter_rejects(tmp_path: Path):
    from src.application.use_case.pre_open_screen_use_case import PreOpenFilterReject

    db = tmp_path / "obs.db"
    repo = SQLiteCandidateObservationsRepository(db)
    persister = PreOpenObservationPersister(repo, PreOpenDirectionalBaselineConfig())
    run_date = date(2026, 6, 18)
    response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=run_date,
            iev_min=100_000,
            total_movers_seen=2,
            candidates=[],
        ),
        warnings=["XYZ: SKIP_SPECULATIVE"],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=run_date, candle_end=None, broker_end=None
        ),
        filter_rejects=(
            PreOpenFilterReject(
                ticker="XYZ",
                screen_result="rejected_filter_speculative",
                reason="suffix",
                iev=150_000,
            ),
        ),
        source_status=PreOpenSourceStatus.LIVE_SUCCESS,
        source_is_live=True,
        capture_phase="NCP_LOCKED",
        collection_started_at=datetime(2026, 6, 18, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta")),
        decision_at=datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
        decision_snapshot_ref="test:ncp:reject",
    )
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(iev_min=100_000, fast_mode=True),
        run_date=run_date,
    )
    n = persister.persist(
        response,
        request,
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
    )
    assert n == 1
    rows = [r for r in repo.list_canonical_by_date(run_date) if r.workflow == PRE_OPEN_WORKFLOW]
    assert len(rows) == 1
    assert rows[0].payload["screen_result"] == "rejected_filter_speculative"
