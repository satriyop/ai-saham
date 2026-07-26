"""Unit tests for ScreenAssessmentPipeline orchestration and hard guards."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.application.services.screen_assessment_pipeline import ScreenAssessmentPipeline
from src.application.services.screen_policy import RiskMode, ScreenPolicy
from src.application.services.signal_inputs import SignalInputs
from src.domain.value_objects.evidence_source_availability import (
    AuthorityDenominatorScope,
)
from src.domain.value_objects.signal_assessment import SignalContext


def _signal_inputs(*, with_evidence: bool) -> SignalInputs:
    ctx = SignalContext(ticker="BBCA", snapshot_date=date(2026, 6, 27))
    evidence = MagicMock(name="canonical_evidence") if with_evidence else None
    return SignalInputs(
        signal_context=ctx,
        canonical_evidence=evidence,
        setup_family="foreign-bounce",
        setup_phase=None,
        authority_denominator_scope=AuthorityDenominatorScope.ATTACHED_REQUIRED,
    )


def test_evaluate_signal_skipped_when_signal_not_applicable():
    engine = MagicMock()
    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.pre_open_tier1_only(),
        signal_engine=engine,
    )

    result = pipeline.evaluate_signal(
        ticker="BBCA",
        inputs=_signal_inputs(with_evidence=True),
    )

    assert result is None
    engine.evaluate_accumulation_discovery.assert_not_called()


def test_evaluate_signal_skipped_when_canonical_evidence_absent():
    engine = MagicMock()
    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.accumulation(),
        signal_engine=engine,
    )

    result = pipeline.evaluate_signal(
        ticker="BBCA",
        inputs=_signal_inputs(with_evidence=False),
    )

    assert result is None
    engine.evaluate_accumulation_discovery.assert_not_called()


def test_evaluate_signal_invokes_engine_when_applicable_and_evidence_present():
    engine = MagicMock()
    engine.evaluate_accumulation_discovery.return_value = MagicMock(name="signal_response")
    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.accumulation(),
        signal_engine=engine,
    )
    inputs = _signal_inputs(with_evidence=True)

    result = pipeline.evaluate_signal(ticker="BBCA", inputs=inputs)

    assert result is engine.evaluate_accumulation_discovery.return_value
    engine.evaluate_accumulation_discovery.assert_called_once()
    call_kwargs = engine.evaluate_accumulation_discovery.call_args
    assert call_kwargs[0][0] == "BBCA"
    assert call_kwargs[1]["canonical_evidence"] is inputs.canonical_evidence


def test_evaluate_pre_open_signal_invokes_single_engine_lane():
    engine = MagicMock()
    engine.evaluate_pre_open_auction_direction.return_value = MagicMock(name="pre_open_result")
    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.pre_open(),
        signal_engine=engine,
    )
    inputs = MagicMock(name="pre_open_inputs")
    market_context = MagicMock(name="market_context")

    result = pipeline.evaluate_pre_open_signal(
        inputs,
        market_context=market_context,
    )

    assert result is engine.evaluate_pre_open_auction_direction.return_value
    engine.evaluate_pre_open_auction_direction.assert_called_once_with(
        inputs,
        market_context=market_context,
    )


def test_compose_trade_setup_skipped_when_not_applicable():
    trade_uc = MagicMock()
    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.pre_open_tier1_only(),
        trade_setup_uc=trade_uc,
    )

    result = pipeline.compose_trade_setup(
        ticker="BBCA",
        as_of_date=date(2026, 6, 27),
        signal_response=MagicMock(),
        risk_response=MagicMock(),
    )

    assert result is None
    trade_uc.execute.assert_not_called()


def test_assess_risk_uses_prebuilt_gate_context_path():
    gate = MagicMock(name="gate_context")
    risk_uc = MagicMock()
    risk_uc.execute.return_value = MagicMock(name="risk_response")
    builder = MagicMock()
    builder.build.return_value = gate

    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.accumulation(),
        risk_use_case=risk_uc,
        risk_inputs_builder=builder,
    )
    candidate = SimpleNamespace(ticker="BBCA")

    resp = pipeline.assess_risk(candidate, as_of_date=date(2026, 6, 27))

    assert resp is risk_uc.execute.return_value
    risk_uc.execute.assert_called_once()
    req = risk_uc.execute.call_args[0][0]
    assert req.ticker == "BBCA"
    assert req.gate_context is gate


def test_assess_risk_self_fetch_when_builder_returns_none():
    risk_engine = MagicMock()
    risk_engine.assess.return_value = MagicMock(name="risk_response")
    builder = MagicMock()
    builder.build.return_value = None

    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy.pre_open_tier1_only(),
        risk_engine=risk_engine,
        risk_inputs_builder=builder,
    )
    candidate = SimpleNamespace(ticker="BBRI")
    mc = MagicMock(name="market_context")

    resp = pipeline.assess_risk(candidate, as_of_date=date(2026, 6, 27), market_context=mc)

    assert resp is risk_engine.assess.return_value
    risk_engine.assess.assert_called_once_with(
        "BBRI", as_of_date=date(2026, 6, 27), market_context=mc
    )


def test_attach_risk_annotate_never_drops_candidates():
    risk_uc = MagicMock()
    risk_uc.execute.return_value = MagicMock(
        assessment=MagicMock(),
        gate_evaluations=[],
        gate_context_completeness=None,
    )
    builder = MagicMock()
    builder.build.return_value = MagicMock()

    pipeline = ScreenAssessmentPipeline(
        policy=ScreenPolicy(
            signal_applicable=False,
            trade_setup_applicable=False,
            risk_mode=RiskMode.ANNOTATE,
        ),
        risk_use_case=risk_uc,
        risk_inputs_builder=builder,
    )
    candidates = [
        SimpleNamespace(
            ticker="A",
            risk_assessment=None,
            risk_gate_evaluations=None,
            risk_gate_context_completeness=None,
            signal_assessment=None,
            trade_setup=None,
        ),
        SimpleNamespace(
            ticker="B",
            risk_assessment=None,
            risk_gate_evaluations=None,
            risk_gate_context_completeness=None,
            signal_assessment=None,
            trade_setup=None,
        ),
    ]

    pipeline.attach_risk_and_trade_setup(candidates, date(2026, 6, 27))

    assert len(candidates) == 2
    assert candidates[0].risk_assessment is not None
    assert candidates[1].risk_assessment is not None
