from datetime import date
from types import SimpleNamespace

from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
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


_FULL_BREAKDOWN = {
    "cons": 40.0,
    "streak": 19.0,
    "vwap": 20.0,
    "rsi": 10.0,
    "flow": 10.0,
    "bb": 10.0,
    "inst": 15.0,
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
    max_breakdown = {"cons": 40.0, "streak": 30.0, "vwap": 20.0, "flow": 10.0, "inst": 15.0}
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
    # cons+streak+vwap+flow+inst = 40+19+20+10+15 (bb & rsi excluded)
    assert evidence.flow_score_ex_bb == 104.0


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
