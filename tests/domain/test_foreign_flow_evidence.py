from datetime import date

from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence
from src.domain.value_objects.foreign_flow_score_breakdown import ForeignFlowScoreBreakdown


def _foreign_flow_score_breakdown(
    *,
    score: float,
    streak: int,
    avg_flow_ratio: float | None,
    vwap_discount_pct: float | None,
    bb_width_pctile: float | None,
    breakdown: tuple[tuple[str, float], ...] = (),
) -> ForeignFlowScoreBreakdown:
    return ForeignFlowScoreBreakdown(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 29),
        foreign_flow_score=score,
        max_score=120.0,
        net_buy_ratio=0.7,
        consecutive_streak=streak,
        vwap_discount_pct=vwap_discount_pct,
        avg_flow_ratio=avg_flow_ratio,
        bb_width_pctile=bb_width_pctile,
        breakdown=breakdown,
    )


def test_foreign_flow_evidence_classifies_positive_confirmed_flow():
    evidence = ForeignFlowEvidence.from_score_breakdown(
        _foreign_flow_score_breakdown(
            score=72.0,
            streak=4,
            avg_flow_ratio=8.5,
            vwap_discount_pct=3.2,
            bb_width_pctile=0.18,
            breakdown=(("cons", 28.6), ("flow", 4.2)),
        ),
        net_buy_days=5,
        total_days=7,
        vwap_pct=-1.1,
    )

    assert evidence.composite_score == 72.0
    assert evidence.score_family == "composite_foreign_flow"
    assert evidence.flow_direction == "POSITIVE"
    assert evidence.confirmation_status == "CONFIRMED"
    assert evidence.to_dict()["component_breakdown"] == {"cons": 28.6, "flow": 4.2}


def test_foreign_flow_evidence_keeps_watch_zone_separate_from_negative_flow():
    evidence = ForeignFlowEvidence.from_score_breakdown(
        _foreign_flow_score_breakdown(
            score=43.0,
            streak=2,
            avg_flow_ratio=-6.0,
            vwap_discount_pct=2.5,
            bb_width_pctile=0.4,
        ),
        net_buy_days=3,
        total_days=7,
        vwap_pct=1.0,
    )

    assert evidence.confirmation_status == "WATCH_ZONE"
    assert evidence.flow_direction == "NEGATIVE"


def test_foreign_flow_evidence_weak_when_score_below_watch_zone():
    evidence = ForeignFlowEvidence.from_score_breakdown(
        _foreign_flow_score_breakdown(
            score=28.0,
            streak=0,
            avg_flow_ratio=None,
            vwap_discount_pct=None,
            bb_width_pctile=None,
        ),
        net_buy_days=1,
        total_days=7,
        vwap_pct=None,
    )

    assert evidence.confirmation_status == "WEAK"
    assert evidence.flow_direction == "UNKNOWN"


def test_foreign_flow_evidence_longer_term_context_is_hashable_and_serializes_as_dict():
    evidence = ForeignFlowEvidence.from_score_breakdown(
        _foreign_flow_score_breakdown(
            score=72.0,
            streak=4,
            avg_flow_ratio=8.5,
            vwap_discount_pct=3.2,
            bb_width_pctile=0.18,
        ),
        net_buy_days=5,
        total_days=7,
        vwap_pct=-1.1,
        longer_term_context={
            "window": 30,
            "labels": ["positive", "confirmed"],
            "nested": {"net": 12.5},
        },
    )

    assert isinstance(hash(evidence), int)
    assert evidence.longer_term_context == (
        ("labels", ("positive", "confirmed")),
        ("nested", (("net", 12.5),)),
        ("window", 30),
    )
    assert evidence.to_dict()["longer_term_context"] == {
        "window": 30,
        "labels": ["positive", "confirmed"],
        "nested": {"net": 12.5},
    }
