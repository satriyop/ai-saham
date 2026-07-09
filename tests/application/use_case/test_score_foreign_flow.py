from datetime import date

from src.application.use_case.score_foreign_flow_use_case import (
    EvidenceComponentPolicy,
    ForeignFlowScorePolicy,
    ScoreForeignFlowRequest,
    ScoreForeignFlowUseCase,
)


def test_score_foreign_flow_matches_legacy_breakdown_shape():
    uc = ScoreForeignFlowUseCase()

    resp = uc.execute(
        ScoreForeignFlowRequest(
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
    # Rescaled 0-120 -> 0-100 (ADR-039). bb_squeeze is disabled by default
    # (see BB ownership fix): "bb" key remains with 0.0.
    assert evidence.foreign_flow_score == 94.9
    assert evidence.breakdown_dict == {
        "cons": 33.3,
        "streak": 15.8,
        "vwap": 16.7,
        "rsi": 8.3,
        "flow": 8.3,
        "bb": 0.0,
        "inst": 12.5,
    }


def test_score_foreign_flow_can_disable_component():
    policy = ForeignFlowScorePolicy(
        consistency=EvidenceComponentPolicy(enabled=False, weight=33.3),
    )
    uc = ScoreForeignFlowUseCase(policy)

    resp = uc.execute(
        ScoreForeignFlowRequest(
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
    assert resp.evidence.foreign_flow_score == 4.2
