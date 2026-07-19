from datetime import date

from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence
from src.domain.value_objects.foreign_flow_score_breakdown import (
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
    ForeignFlowScoreBreakdown,
)


def _comp(key: str, points: float | None, max_points: float, status: ForeignFlowComponentStatus):
    return ForeignFlowComponentScore(
        key=key,
        score_points=points,
        max_points=max_points,
        status=status,
    )


def _foreign_flow_score_breakdown(
    *,
    score: float,
    streak: int,
    avg_flow_ratio: float | None,
    vwap_discount_pct: float | None,
    bb_width_pctile: float | None,
    components: tuple[ForeignFlowComponentScore, ...] = (),
) -> ForeignFlowScoreBreakdown:
    max_by_key = {
        "cons": 33.3,
        "streak": 25.0,
        "vwap": 16.7,
        "rsi": 8.3,
        "flow": 8.3,
        "bb": 8.3,
        "inst": 12.5,
    }
    raw_available = {
        "cons": True,
        "streak": True,
        "vwap": vwap_discount_pct is not None,
        "rsi": False,
        "flow": avg_flow_ratio is not None,
        "bb": bb_width_pctile is not None,
        "inst": False,
    }
    supplied = {component.key: component for component in components}
    remaining = score
    complete: list[ForeignFlowComponentScore] = []
    for key in ("cons", "streak", "vwap", "rsi", "flow", "bb", "inst"):
        if key in supplied:
            complete.append(supplied[key])
            remaining -= supplied[key].score_points or 0.0
            continue
        if raw_available[key]:
            points = min(max(remaining, 0.0), max_by_key[key])
            remaining -= points
            complete.append(
                _comp(key, points, max_by_key[key], ForeignFlowComponentStatus.AVAILABLE)
            )
        else:
            complete.append(
                _comp(key, None, max_by_key[key], ForeignFlowComponentStatus.MISSING)
            )
    if round(max(remaining, 0.0), 1) != 0.0:
        raise AssertionError("test fixture cannot represent requested score")
    return ForeignFlowScoreBreakdown(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 29),
        max_score=100.0,
        net_buy_ratio=0.7,
        consecutive_streak=streak,
        vwap_discount_pct=vwap_discount_pct,
        avg_flow_ratio=avg_flow_ratio,
        bb_width_pctile=bb_width_pctile,
        components=tuple(complete),
    )


def test_foreign_flow_evidence_classifies_positive_confirmed_flow():
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
    )

    assert evidence.composite_score == 72.0
    assert evidence.score_family == "composite_foreign_flow"
    assert evidence.flow_direction == "POSITIVE"
    assert evidence.confirmation_status == "CONFIRMED"
    assert evidence.to_dict()["components"]
    assert evidence.component_coverage < 1.0


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


def test_missing_and_zero_components_remain_distinct_in_evidence():
    missing = ForeignFlowEvidence.from_score_breakdown(
        _foreign_flow_score_breakdown(
            score=33.3,
            streak=0,
            avg_flow_ratio=None,
            vwap_discount_pct=None,
            bb_width_pctile=None,
        ),
        net_buy_days=5,
        total_days=7,
    )
    zero = ForeignFlowEvidence.from_score_breakdown(
        _foreign_flow_score_breakdown(
            score=33.3,
            streak=0,
            avg_flow_ratio=0.0,
            vwap_discount_pct=0.0,
            bb_width_pctile=None,
        ),
        net_buy_days=5,
        total_days=7,
    )

    assert {"vwap", "flow"} <= set(missing.missing_components)
    assert "vwap" not in zero.missing_components
    assert "flow" not in zero.missing_components
    assert missing.component_coverage < 1.0
    assert zero.component_coverage > missing.component_coverage
    assert missing.to_dict()["components"] != zero.to_dict()["components"]
