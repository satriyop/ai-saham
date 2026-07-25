"""Phase 2: pre-open NCP freeze observations (ADR-048)."""

from __future__ import annotations

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
from src.application.services.pre_open_signal_config import PreOpenSignalConfig
from src.application.services.pre_open_screen_config import PreOpenScreenConfig
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
        entry_range_low=Decimal("9900"),
        entry_range_high=Decimal("10100"),
        bid_offer_imbalance=0.6,
        spread_pct=Decimal("0.4"),
    )


def test_derive_screen_result_funnel():
    assert (
        derive_pre_open_screen_result(
            has_entry_range=False, signal_summary=None, trade_setup=None
        )
        == "rejected_plan"
    )
    assert (
        derive_pre_open_screen_result(
            has_entry_range=True, signal_summary=None, trade_setup=None
        )
        == "rejected_auction_missing"
    )
    sig = PreOpenSignalSummary(
        score=80, strength="STRONG", entry_quality="AVOID"
    )
    assert (
        derive_pre_open_screen_result(
            has_entry_range=True, signal_summary=sig, trade_setup=None
        )
        == "rejected_signal"
    )
    sig_ok = PreOpenSignalSummary(
        score=80, strength="STRONG", entry_quality="ENTER"
    )
    assert (
        derive_pre_open_screen_result(
            has_entry_range=True, signal_summary=sig_ok, trade_setup=None
        )
        == "pass"
    )


def test_persist_freeze_and_identity_upsert(tmp_path: Path):
    db = tmp_path / "obs.db"
    repo = SQLiteCandidateObservationsRepository(db)
    persister = PreOpenObservationPersister(repo, PreOpenSignalConfig())

    run_date = date(2026, 6, 18)
    cand = _candidate()
    sig = PreOpenSignalSummary(
        score=72, strength="STRONG", entry_quality="ENTER", signal_authority_coverage=1.0
    )
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
    )
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(iev_min=100_000, top_n=5, fast_mode=True),
        run_date=run_date,
        capture_phase="NCP_LOCKED",
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
    assert row.payload["trade_setup"]["action"] == "ENTER"
    assert row.payload["screen_result"] == "pass"
    assert row.decision_at is not None
    assert row.decision_at.hour == 8 and row.decision_at.minute == 57

    # Same identity upsert replaces, does not duplicate
    n2 = persister.persist(
        response,
        request,
        captured_at=datetime(2026, 6, 18, 8, 58, tzinfo=ZoneInfo("Asia/Jakarta")),
    )
    assert n2 == 1
    rows2 = [r for r in repo.list_canonical_by_date(run_date) if r.workflow == PRE_OPEN_WORKFLOW]
    assert len(rows2) == 1
    # Freeze: score still from payload write (same content)
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
    persister = PreOpenObservationPersister(repo, PreOpenSignalConfig())
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
    )
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(iev_min=100_000, fast_mode=True),
        run_date=run_date,
        capture_phase="NCP_LOCKED",
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
