from datetime import date
from types import SimpleNamespace

from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.use_case.score_foreign_flow_use_case import (
    BciEvidencePolicy,
    EvidenceComponentPolicy,
    ForeignFlowScorePolicy,
    LinearSaturationPolicy,
    StreakEvidencePolicy,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness


def _flow_evidence(breakdown, confirmation_status="CONFIRMED", flow_direction="POSITIVE"):
    return SimpleNamespace(
        component_breakdown=tuple(breakdown.items()),
        confirmation_status=confirmation_status,
        flow_direction=flow_direction,
    )


def _candidate(
    *,
    flow_evidence=None,
    bandar_detector=None,
    bci_label=None,
    bci_tier1_count=0,
    ticker="BBCA",
    latest_candle_date=date(2026, 6, 25),
):
    return SimpleNamespace(
        ticker=ticker,
        foreign_flow_evidence=flow_evidence,
        bandar_detector=bandar_detector,
        bci_label=bci_label,
        bci_tier1_count=bci_tier1_count,
        latest_candle_date=latest_candle_date,
    )


# Rescaled 0-120 -> 0-100 (ADR-039).
_FULL_BREAKDOWN = {
    "cons": 33.3,
    "streak": 15.8,
    "vwap": 16.7,
    "rsi": 8.3,
    "flow": 8.3,
    "bb": 8.3,
    "inst": 12.5,
}


def test_all_sub_signals_present():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    keys = [s.key for s in evidence.flow_signals]
    assert keys == ["cons", "streak", "vwap", "flow", "inst"]


def test_bb_excluded_from_flow_signals():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    assert "bb" not in {s.key for s in evidence.flow_signals}


def test_rsi_excluded_from_flow_signals():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    assert "rsi" not in {s.key for s in evidence.flow_signals}


def test_flow_signals_are_fresh_when_evidence_present():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    assert all(s.freshness == Freshness.FRESH for s in evidence.flow_signals)
    assert evidence.group_freshness == Freshness.FRESH


def test_flow_signals_are_missing_when_no_evidence():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=None)

    evidence = builder.build(candidate)

    assert all(s.freshness == Freshness.MISSING for s in evidence.flow_signals)
    assert evidence.group_freshness == Freshness.MISSING
    assert evidence.confirmation_status == "WEAK"


def test_bandar_fresh_when_snapshot_present():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(
        flow_evidence=_flow_evidence(_FULL_BREAKDOWN),
        bandar_detector=SimpleNamespace(broad_score=8),
    )

    evidence = builder.build(candidate)

    assert evidence.bandar_freshness == Freshness.FRESH
    assert evidence.bandar_broad_score == 8


def test_bandar_missing_when_no_snapshot():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(
        flow_evidence=_flow_evidence(_FULL_BREAKDOWN),
        bandar_detector=None,
    )

    evidence = builder.build(candidate)

    assert evidence.bandar_freshness == Freshness.MISSING
    assert evidence.bandar_broad_score is None
    assert evidence.bandar_direction == Direction.NEUTRAL


def test_bandar_direction_mapping():
    builder = FlowConfirmationEvidenceBuilder()
    flow = _flow_evidence(_FULL_BREAKDOWN)

    bullish = builder.build(_candidate(flow_evidence=flow, bandar_detector=SimpleNamespace(broad_score=5)))
    bearish = builder.build(_candidate(flow_evidence=flow, bandar_detector=SimpleNamespace(broad_score=-5)))
    neutral = builder.build(_candidate(flow_evidence=flow, bandar_detector=SimpleNamespace(broad_score=0)))

    assert bullish.bandar_direction == Direction.BULLISH
    assert bearish.bandar_direction == Direction.BEARISH
    assert neutral.bandar_direction == Direction.NEUTRAL


def test_group_cap_applied():
    builder = FlowConfirmationEvidenceBuilder()
    # Max-bullish flow + max-bullish bandar would push uncapped strength high.
    # Rescaled 0-120 -> 0-100 (ADR-039) — max weight per component.
    max_breakdown = {"cons": 33.3, "streak": 25.0, "vwap": 16.7, "flow": 8.3, "inst": 12.5}
    candidate = _candidate(
        flow_evidence=_flow_evidence(max_breakdown),
        bandar_detector=SimpleNamespace(broad_score=12),
    )

    evidence = builder.build(candidate)

    assert evidence.capped_strength <= evidence.group_cap
    assert evidence.capped_strength <= evidence.uncapped_strength


def test_flow_score_ex_bb_sum():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    expected = round(sum(s.score for s in evidence.flow_signals), 1)
    assert evidence.flow_score_ex_bb == expected
    # cons+streak+vwap+flow+inst = 33.3+15.8+16.7+8.3+12.5 (bb & rsi excluded)
    assert evidence.flow_score_ex_bb == 86.6


def test_to_dict_structure():
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(
        flow_evidence=_flow_evidence(_FULL_BREAKDOWN),
        bandar_detector=SimpleNamespace(broad_score=6),
        bci_label="CLUSTER",
        bci_tier1_count=3,
    )

    d = builder.build(candidate).to_dict()

    expected_keys = {
        "ticker",
        "snapshot_date",
        "flow_signals",
        "flow_score_ex_bb",
        "confirmation_status",
        "flow_direction",
        "bandar_broad_score",
        "bandar_direction",
        "bandar_freshness",
        "bci_label",
        "bci_tier1_count",
        "uncapped_strength",
        "capped_strength",
        "group_cap",
        "group_freshness",
    }
    assert expected_keys <= set(d.keys())
    assert d["bandar_direction"] == "BULLISH"
    assert d["group_freshness"] == "FRESH"
    assert d["flow_direction"] == "POSITIVE"
    assert isinstance(d["flow_signals"], list)
    assert d["flow_signals"][0]["freshness"] == "FRESH"


def test_flow_direction_extracted_from_evidence():
    builder = FlowConfirmationEvidenceBuilder()

    pos = builder.build(_candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN, flow_direction="POSITIVE")))
    neg = builder.build(_candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN, flow_direction="NEGATIVE")))
    flat = builder.build(_candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN, flow_direction="FLAT")))
    missing = builder.build(_candidate(flow_evidence=None))

    assert pos.flow_direction == "POSITIVE"
    assert neg.flow_direction == "NEGATIVE"
    assert flat.flow_direction == "FLAT"
    assert missing.flow_direction == "UNKNOWN"


# ── A. Default policy preserves current behavior ──────────────────────────────

def test_default_policy_weights_match_score_foreign_flow_use_case_defaults():
    """Weights must be derived from ForeignFlowScorePolicy, not a hardcoded copy."""
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    weights = {s.key: s.weight for s in evidence.flow_signals}
    assert weights == {
        "cons": 33.3,
        "streak": 25.0,
        "vwap": 16.7,
        "flow": 8.3,
        "inst": 12.5,
    }


def test_default_policy_max_denominator_is_95_8():
    builder = FlowConfirmationEvidenceBuilder()
    assert builder._flow_max_score == 95.8


def test_default_policy_proportional_strength_matches_known_example():
    """Regression guard for the ADR-039 drift bug: a candidate whose old
    proportional strength was 0.904 must compute to ~0.904 again, not 0.753."""
    builder = FlowConfirmationEvidenceBuilder()
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    assert evidence.flow_score_ex_bb == 86.6
    assert evidence.uncapped_strength == round(86.6 / 95.8, 4)
    assert abs(evidence.uncapped_strength - 0.904) < 0.001


# ── B. Custom policy changes denominator ───────────────────────────────────────

def _custom_policy() -> ForeignFlowScorePolicy:
    return ForeignFlowScorePolicy(
        consistency=EvidenceComponentPolicy(enabled=True, weight=50.0),
        streak=StreakEvidencePolicy(enabled=True, weight=20.0),
        vwap_discount=LinearSaturationPolicy(enabled=True, weight=10.0),
        foreign_flow_ratio=LinearSaturationPolicy(enabled=True, weight=5.0),
        bci=BciEvidencePolicy(enabled=True, cluster_points=15.0, stable_points=5.0),
    )


def test_custom_policy_sub_signal_weights_reflect_policy():
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=_custom_policy())
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    weights = {s.key: s.weight for s in evidence.flow_signals}
    assert weights == {
        "cons": 50.0,
        "streak": 20.0,
        "vwap": 10.0,
        "flow": 5.0,
        "inst": 15.0,
    }


def test_custom_policy_denominator_reflects_policy():
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=_custom_policy())
    assert builder._flow_max_score == 100.0


def test_custom_policy_strength_uses_custom_denominator():
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=_custom_policy())
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    expected_strength = round(evidence.flow_score_ex_bb / 100.0, 4)
    assert evidence.uncapped_strength == expected_strength


# ── C. Disabled component handling ─────────────────────────────────────────────

def test_disabled_component_gets_zero_max_weight():
    policy = ForeignFlowScorePolicy(
        foreign_flow_ratio=LinearSaturationPolicy(enabled=False, weight=8.3),
    )
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=policy)
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    flow_signal = next(s for s in evidence.flow_signals if s.key == "flow")
    assert flow_signal.weight == 0.0


def test_disabled_component_excluded_from_denominator():
    policy = ForeignFlowScorePolicy(
        foreign_flow_ratio=LinearSaturationPolicy(enabled=False, weight=8.3),
    )
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=policy)

    # 33.3 + 25.0 + 16.7 + 0.0(disabled) + 12.5 = 87.5
    assert builder._flow_max_score == 87.5


def test_disabled_component_score_is_zeroed_even_if_breakdown_carries_a_value():
    """Defense in depth: even if the breakdown (stale, malformed, or from a
    custom caller) still carries a nonzero score for a policy-disabled key,
    the builder must not let it leak into the numerator. In production
    ScoreForeignFlowUseCase always emits 0.0 for a disabled component, but
    this builder does not control every caller of build()."""
    policy = ForeignFlowScorePolicy(
        foreign_flow_ratio=LinearSaturationPolicy(enabled=False, weight=8.3),
    )
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=policy)
    # _FULL_BREAKDOWN["flow"] == 8.3 (nonzero) despite the component being
    # disabled in the policy passed to this builder.
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN))

    evidence = builder.build(candidate)

    flow_signal = next(s for s in evidence.flow_signals if s.key == "flow")
    assert flow_signal.weight == 0.0
    assert flow_signal.score == 0.0
    # numerator excludes the disabled component's score, denominator excludes its weight
    assert evidence.flow_score_ex_bb == round(86.6 - 8.3, 1)
    assert evidence.uncapped_strength == round(evidence.flow_score_ex_bb / 87.5, 4)


# ── D. All included components disabled ────────────────────────────────────────

def _all_disabled_policy() -> ForeignFlowScorePolicy:
    return ForeignFlowScorePolicy(
        consistency=EvidenceComponentPolicy(enabled=False, weight=33.3),
        streak=StreakEvidencePolicy(enabled=False, weight=25.0),
        vwap_discount=LinearSaturationPolicy(enabled=False, weight=16.7),
        foreign_flow_ratio=LinearSaturationPolicy(enabled=False, weight=8.3),
        bci=BciEvidencePolicy(enabled=False, cluster_points=12.5, stable_points=4.2),
    )


def test_all_disabled_denominator_is_zero():
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=_all_disabled_policy())
    assert builder._flow_max_score == 0.0


def test_all_disabled_flow_strength_is_zero_without_bandar():
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=_all_disabled_policy())
    candidate = _candidate(flow_evidence=_flow_evidence(_FULL_BREAKDOWN), bandar_detector=None)

    evidence = builder.build(candidate)

    assert evidence.uncapped_strength == 0.0
    assert evidence.capped_strength == 0.0


def test_all_disabled_bandar_strength_still_works():
    """Even with a zero flow denominator, bandar contribution must still be
    computed correctly (not skipped or zeroed out by the flow-side guard)."""
    builder = FlowConfirmationEvidenceBuilder(foreign_flow_score_policy=_all_disabled_policy())
    candidate = _candidate(
        flow_evidence=_flow_evidence(_FULL_BREAKDOWN),
        bandar_detector=SimpleNamespace(broad_score=12),
    )

    evidence = builder.build(candidate)

    # flow_strength=0.0, bandar_strength=(12+12)/(2*12)=1.0 -> avg=0.5
    assert evidence.uncapped_strength == 0.5
