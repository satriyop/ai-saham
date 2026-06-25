from datetime import date

from src.application.use_case.assess_accumulation_evidence_use_case import (
    AssessAccumulationEvidenceRequest,
    AssessAccumulationEvidenceUseCase,
    AccumulationEvidencePolicy,
    EvidenceComponentPolicy,
)


def test_assess_accumulation_evidence_matches_legacy_breakdown_shape():
    uc = AssessAccumulationEvidenceUseCase()

    resp = uc.execute(
        AssessAccumulationEvidenceRequest(
            ticker="BBCA",
            snapshot_date=date(2026, 6, 25),
            net_buy_ratio=1.0,
            consecutive_streak=7,
            vwap_discount_pct=10.0,
            rsi=40.0,
            avg_flow_ratio=20.0,
            bb_width_pctile=0.0,
            bci_label="CLUSTER",
            bci_tier1_count=3,
        )
    )

    evidence = resp.evidence
    assert evidence.accum_score == 120.0
    assert evidence.breakdown_dict == {
        "cons": 40.0,
        "streak": 19.0,
        "vwap": 20.0,
        "rsi": 10.0,
        "flow": 10.0,
        "bb": 10.0,
        "inst": 15.0,
    }


def test_assess_accumulation_evidence_can_disable_component():
    policy = AccumulationEvidencePolicy(
        consistency=EvidenceComponentPolicy(enabled=False, weight=40.0),
    )
    uc = AssessAccumulationEvidenceUseCase(policy)

    resp = uc.execute(
        AssessAccumulationEvidenceRequest(
            ticker="BBCA",
            snapshot_date=date(2026, 6, 25),
            net_buy_ratio=1.0,
            consecutive_streak=0,
            vwap_discount_pct=0.0,
            rsi=None,
            avg_flow_ratio=0.0,
            bb_width_pctile=None,
            bci_label=None,
        )
    )

    assert resp.evidence.breakdown_dict["cons"] == 0.0
    assert resp.evidence.accum_score == 5.0
