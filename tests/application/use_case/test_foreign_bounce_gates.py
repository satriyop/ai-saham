"""Tests for foreign-bounce setup evaluation and compute_percent_plan."""

from decimal import Decimal

import pytest

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.accumulation_trade_plan import compute_percent_plan
from src.application.use_case.evaluate_swing_setup_use_case import (
    COILED_SPRING_SETUP,
    FOREIGN_BOUNCE_SETUP,
    PULLBACK_CONTINUATION_SETUP,
    SMART_MONEY_CONFIRMED_SETUP,
    CoiledSpringSetupConfig,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
    ForeignBounceSetupConfig,
    PullbackContinuationSetupConfig,
    SmartMoneyConfirmedSetupConfig,
    SwingSetupCatalogConfig,
)
from src.domain.value_objects.setup_evaluation import SetupMatch

# ── helpers ────────────────────────────────────────────────────────────────────

def _candidate(**kwargs) -> AccumulationCandidate:
    from decimal import Decimal
    defaults = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.71,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("9000"),
        current_price=Decimal("8640"),
        vwap_discount_pct=4.0,
        rsi=45.0,
        trend="SIDE",
        foreign_flow_score=80.0,
        top_brokers=["AK", "BK"],
        institutional_flag=True,
        avg_flow_ratio=6.0,
    )
    defaults.update(kwargs)
    return AccumulationCandidate(**defaults)


_GATE_DEFAULTS = dict(
    gate_min_foreign_flow_score=70.0,
    gate_min_vwap_discount_pct=3.0,
    gate_required_trend="SIDE",
    gate_min_flow_ratio_pct=5.0,
    gate_max_rsi=60.0,
    partial_max_failed_gates=2,
)


def _eval(candidate, **overrides):
    params = {**_GATE_DEFAULTS, **overrides}
    return EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=FOREIGN_BOUNCE_SETUP,
            candidate=candidate,
            config=SwingSetupCatalogConfig(foreign_bounce=ForeignBounceSetupConfig(**params)),
        )
    )


# ── foreign-bounce setup evaluation ────────────────────────────────────────────

def test_all_gates_pass_returns_match():
    c = _candidate()
    evaluation = _eval(c)
    assert evaluation.match == SetupMatch.MATCH
    assert evaluation.failed_reasons == ()


def test_single_gate_fail_returns_partial():
    c = _candidate(rsi=65.0)
    evaluation = _eval(c)
    assert evaluation.match == SetupMatch.PARTIAL
    assert any("RSI" in f for f in evaluation.failed_reasons)


def test_many_gates_fail_returns_no_match():
    c = _candidate(
        rsi=75.0,
        trend="UP",
        avg_flow_ratio=1.0,
        vwap_discount_pct=0.5,
        foreign_flow_score=30.0,
    )
    evaluation = _eval(c)
    assert evaluation.match == SetupMatch.NO_MATCH
    assert len(evaluation.failed_reasons) > 2


def test_passing_score_does_not_bypass_too_many_failed_gates():
    # Score gate passes, but 4 other gates fail (> partial_max_failed_gates=2).
    # Former force_partial_when_score_passes bypass would have forced PARTIAL.
    c = _candidate(
        foreign_flow_score=80.0,
        rsi=75.0,
        trend="UP",
        avg_flow_ratio=1.0,
        vwap_discount_pct=0.5,
    )
    evaluation = _eval(c)
    assert evaluation.match == SetupMatch.NO_MATCH
    assert len(evaluation.failed_reasons) > 2
    assert not any("foreign_flow_score" in f for f in evaluation.failed_reasons)


def test_score_gate_fail_but_few_total_fails_returns_partial():
    # Score fails, but only 1 other gate fails (<= partial_max_failed_gates=2)
    c = _candidate(foreign_flow_score=60.0, rsi=65.0)  # 2 failures: score + RSI
    evaluation = _eval(c)
    assert evaluation.match == SetupMatch.PARTIAL


def test_failed_gates_contain_required_values():
    c = _candidate(rsi=75.0)
    evaluation = _eval(c)
    assert any("<= 60" in f for f in evaluation.failed_reasons)


def test_none_rsi_fails_rsi_present_gate():
    c = _candidate(rsi=None)
    evaluation = _eval(c)
    assert any("RSI present" in f for f in evaluation.failed_reasons)


def test_none_vwap_fails_vwap_gate():
    c = _candidate(vwap_discount_pct=None)
    evaluation = _eval(c)
    assert any("fvwap%" in f for f in evaluation.failed_reasons)


def test_wrong_trend_fails_trend_gate():
    c = _candidate(trend="UP")
    evaluation = _eval(c)
    assert any("trend" in f for f in evaluation.failed_reasons)


def test_custom_gate_values_respected():
    c = _candidate(foreign_flow_score=50.0)
    # With min_foreign_flow_score=40.0, score gate should pass
    evaluation = _eval(c, gate_min_foreign_flow_score=40.0)
    assert not any("score" in f for f in evaluation.failed_reasons)


def test_coiled_spring_match_requires_tight_bb_width():
    c = _candidate(foreign_flow_score=62.0, bb_width_pctile=0.12, avg_flow_ratio=3.5, rsi=58.0)

    evaluation = EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=COILED_SPRING_SETUP,
            candidate=c,
            config=SwingSetupCatalogConfig(
                coiled_spring=CoiledSpringSetupConfig(gate_max_bb_width_pctile=0.20)
            ),
        )
    )

    assert evaluation.match == SetupMatch.MATCH


def test_coiled_spring_rejects_loose_bb_width_when_other_gates_fail():
    c = _candidate(foreign_flow_score=40.0, bb_width_pctile=0.60, avg_flow_ratio=0.5, rsi=72.0)

    evaluation = EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=COILED_SPRING_SETUP,
            candidate=c,
            config=SwingSetupCatalogConfig(),
        )
    )

    assert evaluation.match == SetupMatch.NO_MATCH
    assert any("bb_width_pctile" in reason for reason in evaluation.failed_reasons)


def test_coiled_spring_passing_score_does_not_bypass_too_many_failed_gates():
    c = _candidate(foreign_flow_score=80.0, bb_width_pctile=0.60, avg_flow_ratio=0.5, rsi=72.0)

    evaluation = EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=COILED_SPRING_SETUP,
            candidate=c,
            config=SwingSetupCatalogConfig(),
        )
    )

    assert evaluation.match == SetupMatch.NO_MATCH
    assert len(evaluation.failed_reasons) > 2
    assert not any("foreign_flow_score" in reason for reason in evaluation.failed_reasons)


def test_smart_money_confirmed_requires_broker_detail():
    c = _candidate(foreign_flow_score=70.0)

    evaluation = EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=SMART_MONEY_CONFIRMED_SETUP,
            candidate=c,
            config=SwingSetupCatalogConfig(),
            broker_detail=None,
        )
    )

    assert evaluation.match == SetupMatch.NO_MATCH
    assert any("broker detail" in reason for reason in evaluation.failed_reasons)


def test_smart_money_confirmed_matches_smart_led_flow():
    from types import SimpleNamespace

    c = _candidate(foreign_flow_score=70.0)
    broker_detail = SimpleNamespace(
        smart_flow=Decimal("70000000"),
        noise_flow=Decimal("20000000"),
        neutral_flow=Decimal("10000000"),
        smart_share_pct=70.0,
    )

    evaluation = EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=SMART_MONEY_CONFIRMED_SETUP,
            candidate=c,
            config=SwingSetupCatalogConfig(
                smart_money_confirmed=SmartMoneyConfirmedSetupConfig(
                    gate_min_smart_share_pct=60.0,
                    gate_max_noise_share_pct=30.0,
                )
            ),
            broker_detail=broker_detail,
        )
    )

    assert evaluation.match == SetupMatch.MATCH


def test_pullback_continuation_matches_uptrend_pullback():
    c = _candidate(
        foreign_flow_score=60.0,
        trend="UP",
        avg_flow_ratio=3.0,
        rsi=50.0,
        vwap_discount_pct=-1.0,
    )

    evaluation = EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=PULLBACK_CONTINUATION_SETUP,
            candidate=c,
            config=SwingSetupCatalogConfig(
                pullback_continuation=PullbackContinuationSetupConfig(
                    gate_min_vwap_discount_pct=-2.0
                )
            ),
        )
    )

    assert evaluation.match == SetupMatch.MATCH


# ── compute_percent_plan ───────────────────────────────────────────────────────

def test_percent_plan_basic():
    stop, target = compute_percent_plan(
        Decimal("1000"), stop_pct=Decimal("5"), target_pct=Decimal("5")
    )
    assert stop == pytest.approx(Decimal("950"))
    assert target == pytest.approx(Decimal("1050"))


def test_percent_plan_asymmetric():
    stop, target = compute_percent_plan(
        Decimal("2000"), stop_pct=Decimal("4"), target_pct=Decimal("8")
    )
    assert stop == pytest.approx(Decimal("1920"))
    assert target == pytest.approx(Decimal("2160"))
