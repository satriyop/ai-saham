from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from src.application.services.pre_open_observation_payload import (
    derive_pre_open_screen_result,
)
from src.application.services.pre_open_observation_persister import (
    PreOpenObservationPersister,
)
from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
)
from src.application.use_case.pre_open_screen_use_case import PreOpenFilterReject
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenDataFreshness,
    PreOpenRiskSummary,
    PreOpenSignalSummary,
    PreOpenWorkflowRequest,
    PreOpenWorkflowResponse,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
)
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
from src.domain.value_objects.screener_result import PreOpenScreenResult, ScreenerCandidate
from src.domain.value_objects.signal_assessment import (
    PRE_OPEN_AUCTION_DIRECTION_IDENTITY,
    SignalStrength,
)
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

WIB = ZoneInfo("Asia/Jakarta")


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


def _signal_summary(*, score: int = 80, entry_quality: str = "ENTER") -> PreOpenSignalSummary:
    return PreOpenSignalSummary(
        identity=PRE_OPEN_AUCTION_DIRECTION_IDENTITY,
        contract="pre_open_directional_baseline.v1",
        direction="BULLISH",
        confidence="HIGH",
        auction_quality="RELIABLE",
        raw_score=score,
        score=score,
        strength="STRONG",
        entry_quality=entry_quality,
        factors={"delta_iev": 20_000},
        rationale=("direction:agreement_bullish",),
        quality_reasons=(),
        signal_authority_coverage=1.0,
    )


def _response(*, rejects=()) -> PreOpenWorkflowResponse:
    run_date = date(2026, 6, 18)
    candidate = _candidate()
    signal = _signal_summary(score=72)
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
    return PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=run_date,
            iev_min=100_000,
            total_movers_seen=1 + len(rejects),
            candidates=[candidate],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=run_date, candle_end=None, broker_end=None
        ),
        risk_by_ticker={"BBCA": risk},
        signal_by_ticker={"BBCA": signal},
        trade_setup_by_ticker={"BBCA": setup},
        filter_rejects=tuple(rejects),
        source_status=PreOpenSourceStatus.LIVE_SUCCESS,
        source_is_live=True,
        capture_phase="NCP_LOCKED",
        collection_started_at=datetime(2026, 6, 18, 8, 56, tzinfo=WIB),
        decision_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
        decision_snapshot_ref="test:ncp",
    )


def test_derive_screen_result_funnel() -> None:
    assert (
        derive_pre_open_screen_result(has_entry_range=False, signal_summary=None, trade_setup=None)
        == "rejected_plan"
    )
    assert (
        derive_pre_open_screen_result(
            has_entry_range=True,
            signal_summary=_signal_summary(entry_quality="AVOID"),
            trade_setup=None,
        )
        == "rejected_signal"
    )


def test_persists_database_owned_observation_idempotently(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    persister = PreOpenObservationPersister(repository, PreOpenDirectionalBaselineConfig())
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(iev_min=100_000, top_n=5, fast_mode=True),
        run_date=date(2026, 6, 18),
    )

    first = persister.persist(
        _response(),
        request,
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
    )
    assert first.recorded_count == 1
    assert len(first.observations) == 1
    assert first.observations[0].ticker == "BBCA"
    assert first.observations[0].inserted is True
    assert first.observations[0].observation_id

    second = persister.persist(
        _response(),
        request,
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
    )
    assert second.recorded_count == 0
    assert len(second.observations) == 1
    assert second.observations[0].inserted is False
    assert second.observations[0].observation_id == first.observations[0].observation_id

    rows = repository.list_observations(AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION)
    assert len(rows) == 1
    row = rows[0]
    assert row.contract_id is LearningContractId.PRE_OPEN_OBSERVATION
    assert row.decision_payload["signal"]["score"] == 72
    assert row.decision_payload["trade_setup"]["action"] == "ENTER"
    assert row.decision_payload["candidate"]["iep"] == 10100
    # Absent MarketContext on test response → null market_regime (gate inert for analyze)
    assert row.decision_payload.get("market_regime") is None


def test_persists_market_regime_when_present(tmp_path: Path) -> None:
    from src.domain.value_objects.market_context import MarketContext, MarketRegime

    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(iev_min=100_000, top_n=5, fast_mode=True),
        run_date=date(2026, 6, 18),
    )
    base = _response()
    response = PreOpenWorkflowResponse(
        **{
            **base.__dict__,
            "market_regime": MarketContext(
                as_of_date=date(2026, 6, 18),
                regime=MarketRegime.RISK_ON,
                conviction=0.8,
                factors=(),
                signal_multiplier=1.0,
                gate_tightening=False,
            ),
        }
    )
    PreOpenObservationPersister(repository).persist(
        response,
        request,
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
    )
    row = repository.list_observations(AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION)[0]
    assert row.decision_payload["market_regime"]["regime"] == "RISK_ON"


def test_persists_hard_filter_rejects(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    reject = PreOpenFilterReject(
        ticker="XYZ",
        screen_result="rejected_filter_speculative",
        reason="suffix",
        iev=150_000,
    )
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(iev_min=100_000, fast_mode=True),
        run_date=date(2026, 6, 18),
    )

    result = PreOpenObservationPersister(repository).persist(
        _response(rejects=(reject,)),
        request,
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
    )

    rows = repository.list_observations(AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION)
    assert result.recorded_count == 2
    assert {r.ticker for r in result.observations} == {"BBCA", "XYZ"}
    assert {row.decision_payload["screen_result"] for row in rows} == {
        "pass",
        "rejected_filter_speculative",
    }


def test_no_repository_is_noop() -> None:
    response = _response()
    response = PreOpenWorkflowResponse(
        **{
            **response.__dict__,
            "result": PreOpenScreenResult(
                screened_date=date(2026, 6, 18),
                iev_min=100_000,
                total_movers_seen=0,
                candidates=[],
            ),
            "filter_rejects": (),
        }
    )
    request = PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(fast_mode=True),
        run_date=date(2026, 6, 18),
    )
    empty = PreOpenObservationPersister(None).persist(response, request)
    assert empty.recorded_count == 0
    assert empty.observations == ()
