from src.domain.value_objects.flow_evidence import FlowEvidence


def test_flow_evidence_classifies_positive_confirmed_flow():
    evidence = FlowEvidence.from_accumulation_evidence(
        composite_score=72.0,
        max_score=120.0,
        net_buy_days=5,
        total_days=7,
        streak=4,
        avg_flow_ratio=8.5,
        f_vwap_pct=3.2,
        vwap_pct=-1.1,
        bb_width_pctile=0.18,
        component_breakdown=(("cons", 28.6), ("flow", 4.2)),
    )

    assert evidence.score_family == "composite_flow_evidence"
    assert evidence.flow_direction == "POSITIVE"
    assert evidence.confirmation_status == "CONFIRMED"
    assert evidence.to_dict()["component_breakdown"] == {"cons": 28.6, "flow": 4.2}


def test_flow_evidence_keeps_watch_zone_separate_from_negative_flow():
    evidence = FlowEvidence.from_accumulation_evidence(
        composite_score=43.0,
        max_score=120.0,
        net_buy_days=3,
        total_days=7,
        streak=2,
        avg_flow_ratio=-6.0,
        f_vwap_pct=2.5,
        vwap_pct=1.0,
        bb_width_pctile=0.4,
        component_breakdown=(),
    )

    assert evidence.confirmation_status == "WATCH_ZONE"
    assert evidence.flow_direction == "NEGATIVE"


def test_flow_evidence_weak_when_score_below_watch_zone():
    evidence = FlowEvidence.from_accumulation_evidence(
        composite_score=28.0,
        max_score=120.0,
        net_buy_days=1,
        total_days=7,
        streak=0,
        avg_flow_ratio=None,
        f_vwap_pct=None,
        vwap_pct=None,
        bb_width_pctile=None,
        component_breakdown=(),
    )

    assert evidence.confirmation_status == "WEAK"
    assert evidence.flow_direction == "UNKNOWN"
