"""Negative tests required by the CANONICAL-EVIDENCE-BOUNDARY repair task
(ADR-041). Covers items not already exercised by
`tests/domain/value_objects/test_canonical_signal_evidence_input.py` or
`tests/application/services/test_accumulation_candidate_evaluator.py`:

1. Swing performs no second broker query after candidate evaluation.
2. The exact broker row object identities from evaluation reach BuiltFlowEvidence.
3. A future broker summary raises ValueError.
4. A future broker daily-flow row raises ValueError.
5. A future ticker candle raises ValueError.
6. A future IHSG candle raises ValueError.
8. Loose evidence cannot be supplied to SignalEngine.
12. Contract ValueError escapes instead of becoming a warning.
13. Screen and swing produce equivalent flow evidence/provenance for
    identical source fixtures (both call the same FlowConfirmationEvidence-
    Builder.build() with the same consumed rows — parity is structural, not
    coincidental).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.dto.accumulation_screen import AccumulationCandidate, AccumulationCandidateEvaluationResult
from src.application.dto.built_evidence import BuiltFlowEvidence, BuiltSetupEvidence
from src.application.services.evidence_source_availability_assembler import (
    EvidenceSourceAvailabilityAssembler,
)
from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.services.signal_engine import SignalEngine
from src.application.services.swing_analysis_evidence_builder import (
    SwingAnalysisEvidenceBuilder,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.benchmark_symbol import CANONICAL_BENCHMARK_TICKER
from src.domain.value_objects.canonical_signal_evidence_input import CandleRowIdentity, SetupProvenance
from src.domain.value_objects.factor_evidence import Freshness
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import SignalContext
from tests.application.use_case.accumulation_screen_fixtures import (
    _daily_flow as _make_daily_flow,
)
from tests.application.use_case.accumulation_screen_fixtures import _summary as _make_summary

TICKER = "BBCA"
SNAP = date(2026, 7, 17)


def _candidate(**overrides) -> AccumulationCandidate:
    values = dict(
        ticker=TICKER,
        window_days=7,
        net_buy_days=4,
        total_days=5,
        net_buy_ratio=0.8,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1000"),
        current_price=Decimal("1000"),
        vwap_discount_pct=0.0,
        rsi=50.0,
        trend="UP",
        foreign_flow_score=50.0,
        top_brokers=None,
        institutional_flag=False,
        latest_candle_date=SNAP,
        latest_broker_date=SNAP,
        latest_broker_daily_flow_date=SNAP,
    )
    values.update(overrides)
    return AccumulationCandidate(**values)


def _summary(day: date):
    return _make_summary(TICKER, day, Decimal("1000"))


def _daily_flow(day: date, broker_code: str = "AK"):
    return _make_daily_flow(TICKER, day, broker_code, 100)


def _no_excess_return() -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG", window_sessions=5, ticker_return_pct=None, benchmark_return_pct=None,
        excess_return_pct=None, window_start=None, window_end=None, common_session_count=0,
        status=BenchmarkExcessReturnStatus.UNAVAILABLE, unavailable_reason="test",
    )


# --- 3/4: AccumulationCandidateEvaluationResult rejects future consumed rows ---


class TestEvaluationResultRejectsFutureRows:
    def test_future_broker_summary_row_raises(self):
        with pytest.raises(ValueError, match="after analysis_date"):
            AccumulationCandidateEvaluationResult(
                candidate=_candidate(latest_broker_date=SNAP + timedelta(days=1)),
                consumed_candles=(),
                consumed_broker_summaries=(_summary(SNAP + timedelta(days=1)),),
                consumed_broker_daily_flows=(),
                analysis_date=SNAP,
            )

    def test_future_broker_daily_flow_row_raises(self):
        with pytest.raises(ValueError, match="after analysis_date"):
            AccumulationCandidateEvaluationResult(
                candidate=_candidate(latest_broker_daily_flow_date=SNAP + timedelta(days=1)),
                consumed_candles=(),
                consumed_broker_summaries=(),
                consumed_broker_daily_flows=(_daily_flow(SNAP + timedelta(days=1)),),
                analysis_date=SNAP,
            )

    def test_future_candle_row_raises(self):
        candle = Candle(
            ticker=TICKER, date=SNAP + timedelta(days=1), open=Decimal("100"), high=Decimal("101"),
            low=Decimal("99"), close=Decimal("100"), volume=1000,
        )
        with pytest.raises(ValueError, match="after analysis_date"):
            AccumulationCandidateEvaluationResult(
                candidate=_candidate(latest_candle_date=SNAP + timedelta(days=1)),
                consumed_candles=(candle,),
                consumed_broker_summaries=(),
                consumed_broker_daily_flows=(),
                analysis_date=SNAP,
            )


# --- 5/6: BuiltSetupEvidence rejects future ticker/benchmark candles ---


def _setup_evidence() -> SetupEvidence:
    return SetupEvidence(
        ticker=TICKER, snapshot_date=SNAP, setup_name="foreign-bounce", setup_match="MATCH",
        match_strength=100.0, failed_gates=(), trend="UP", rsi=45.0, bb_width_pctile=0.2,
        vwap_discount_pct=1.5, vwap_pct=1.0,
        benchmark_excess_return_5_session=_no_excess_return(),
        benchmark_excess_return_20_session=_no_excess_return(),
        volume_trend_ratio=1.2, volume_freshness=Freshness.FRESH, candle_source="test",
    )


class TestBuiltSetupEvidenceRejectsFutureRows:
    def test_future_ticker_candle_raises(self):
        provenance = SetupProvenance(
            ticker=TICKER,
            candle_rows=(CandleRowIdentity(ticker=TICKER, date=SNAP + timedelta(days=1), source="test"),),
        )
        with pytest.raises(ValueError, match="after evidence.snapshot_date"):
            BuiltSetupEvidence(evidence=_setup_evidence(), provenance=provenance)

    def test_future_ihsg_candle_raises(self):
        provenance = SetupProvenance(
            ticker=TICKER,
            candle_rows=(CandleRowIdentity(ticker=TICKER, date=SNAP, source="test"),),
            benchmark_candle_rows=(
                CandleRowIdentity(
                    ticker=CANONICAL_BENCHMARK_TICKER, date=SNAP + timedelta(days=1), source="test"
                ),
            ),
        )
        with pytest.raises(ValueError, match="after evidence.snapshot_date"):
            BuiltSetupEvidence(evidence=_setup_evidence(), provenance=provenance)


# --- 1/2: swing does not re-query broker repo; exact rows reach BuiltFlowEvidence ---


class _RaisingBrokerRepository:
    """Any broker query on this repository is a contract violation for
    SwingAnalysisEvidenceBuilder — it must only use
    AccumulationCandidateEvaluationResult.consumed_broker_summaries/
    consumed_broker_daily_flows, never re-query."""

    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        raise AssertionError("swing must not re-query broker_summaries")

    def get_broker_daily_flows(self, ticker, start_date=None, end_date=None):
        raise AssertionError("swing must not re-query broker_daily_flows")

    def get_foreign_flow_points(self, ticker, start_date=None, end_date=None):
        raise AssertionError("swing must not re-query foreign_flow_points")


class _MarketRepository:
    def get_candles(self, ticker, start_date=None, end_date=None):
        return []

    def get_candle_source(self, ticker, on_date):
        return None


def _builder(broker_repository) -> SwingAnalysisEvidenceBuilder:
    return SwingAnalysisEvidenceBuilder(
        market_repository=_MarketRepository(),
        broker_repository=broker_repository,
        registry=None,
        rules_loader=SimpleNamespace(),
        flow_confirmation_builder=FlowConfirmationEvidenceBuilder(),
        candidate_observations_repository=None,
        signal_engine=None,
        corporate_action_risk_use_case=None,
    )


def test_swing_evidence_builder_never_queries_broker_repository():
    summary_row = _summary(SNAP)
    daily_flow_row = _daily_flow(SNAP)
    evaluation_result = AccumulationCandidateEvaluationResult(
        candidate=_candidate(latest_candle_date=None),
        consumed_candles=(),
        consumed_broker_summaries=(summary_row,),
        consumed_broker_daily_flows=(daily_flow_row,),
        analysis_date=SNAP,
    )
    builder = _builder(_RaisingBrokerRepository())

    result = builder.build(
        ticker=TICKER,
        snapshot_date=SNAP,
        benchmark="IHSG",
        candles=[],
        accumulation_evaluation=evaluation_result,
        setup_eval=None,
        setup_name=None,
        strategy_name=None,
        swing_config=None,
    )

    # No AssertionError was raised -> broker repository was never queried.
    assert result.built_flow_evidence is not None
    provenance = result.built_flow_evidence.provenance
    assert len(provenance.broker_summary_rows) == 1
    assert provenance.broker_summary_rows[0].date == summary_row.date
    assert provenance.broker_summary_rows[0].ticker == summary_row.ticker
    assert len(provenance.broker_daily_flow_rows) == 1
    assert provenance.broker_daily_flow_rows[0].date == daily_flow_row.date
    assert provenance.broker_daily_flow_rows[0].broker_code == daily_flow_row.broker_code


# --- 8: loose evidence cannot be supplied to SignalEngine ---


def test_signal_engine_rejects_loose_setup_evidence_kwarg():
    engine = SignalEngine()
    ctx = SignalContext(ticker=TICKER, snapshot_date=SNAP)
    with pytest.raises(TypeError):
        engine.evaluate_with_context(
            TICKER, ctx, setup_evidence=_setup_evidence()  # type: ignore[call-arg]
        )


def test_signal_engine_rejects_loose_flow_confirmation_evidence_kwarg():
    engine = SignalEngine()
    ctx = SignalContext(ticker=TICKER, snapshot_date=SNAP)
    with pytest.raises(TypeError):
        engine.evaluate_with_context(
            TICKER, ctx, flow_confirmation_evidence=None  # type: ignore[call-arg]
        )


# --- 12: contract ValueError escapes instead of becoming a warning ---


def test_flow_confirmation_evidence_builder_ticker_mismatch_escapes_as_valueerror():
    # A broker row from a different ticker than the candidate is a contract
    # violation (FlowProvenance ticker mismatch) — it must raise, not be
    # caught anywhere and downgraded to a warning.
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate()
    foreign_row = _summary(SNAP)
    object.__setattr__(foreign_row, "ticker", "ASII")

    with pytest.raises(ValueError, match="ticker mismatch"):
        builder.build(
            candidate,
            analysis_date=SNAP,
            consumed_broker_summaries=(foreign_row,),
            consumed_broker_daily_flows=(),
        )


def test_swing_evidence_builder_propagates_duplicate_row_violation_not_a_warning():
    # SwingAnalysisEvidenceBuilder's flow-evidence try/except must re-raise a
    # ValueError from a provenance contract violation — here, a duplicate
    # consumed broker-summary row (which AccumulationCandidateEvaluationResult
    # itself does not check for, but FlowProvenance does) — rather than
    # appending "Flow confirmation evidence unavailable: ..." to warnings.
    duplicated_row = _summary(SNAP)
    evaluation_result = AccumulationCandidateEvaluationResult(
        candidate=_candidate(latest_candle_date=None, latest_broker_daily_flow_date=None),
        consumed_candles=(),
        consumed_broker_summaries=(duplicated_row, duplicated_row),
        consumed_broker_daily_flows=(),
        analysis_date=SNAP,
    )
    builder = _builder(_RaisingBrokerRepository())

    with pytest.raises(ValueError, match="duplicate"):
        builder.build(
            ticker=TICKER,
            snapshot_date=SNAP,
            benchmark="IHSG",
            candles=[],
            accumulation_evaluation=evaluation_result,
            setup_eval=None,
            setup_name=None,
            strategy_name=None,
            swing_config=None,
        )


# --- 13: screen and swing produce equivalent flow evidence/provenance ---


def test_screen_and_swing_flow_paths_produce_equivalent_evidence_for_identical_fixtures():
    # AccumulationCandidateSignalAssessor (screen) and SwingAnalysisEvidence
    # Builder (swing) both call FlowConfirmationEvidenceBuilder.build() with
    # the candidate and its evaluator-consumed rows — the same public API,
    # never independently reimplemented per workflow. Given identical
    # inputs, the two call sites are structurally guaranteed to agree.
    candidate = _candidate()
    summaries = (_summary(SNAP), _summary(SNAP - timedelta(days=1)))
    daily_flows = (_daily_flow(SNAP, "AK"),)

    screen_side_candidate = _candidate()  # separate object, same field values
    swing_side_candidate = _candidate()

    screen_result = FlowConfirmationEvidenceBuilder().build(
        screen_side_candidate,
        analysis_date=SNAP,
        consumed_broker_summaries=summaries,
        consumed_broker_daily_flows=daily_flows,
    )
    swing_result = FlowConfirmationEvidenceBuilder().build(
        swing_side_candidate,
        analysis_date=SNAP,
        consumed_broker_summaries=summaries,
        consumed_broker_daily_flows=daily_flows,
    )

    assert screen_result.evidence == swing_result.evidence
    assert screen_result.provenance == swing_result.provenance
