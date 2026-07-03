from datetime import date

from src.application.use_case.score_foreign_flow_use_case import (
    BollingerSqueezePolicy,
    ForeignFlowScorePolicy,
    ScoreForeignFlowRequest,
    ScoreForeignFlowUseCase,
)


def _request(bb_width_pctile):
    return ScoreForeignFlowRequest(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 25),
        net_buy_ratio=1.0,
        consecutive_streak=7,
        vwap_discount_pct=10.0,
        rsi=40.0,
        avg_flow_ratio=20.0,
        bb_width_pctile=bb_width_pctile,
        bci_label="CLUSTER",
        bci_tier1_count=3,
    )


def test_bb_score_zero_at_maximum_squeeze():
    uc = ScoreForeignFlowUseCase()
    resp = uc.execute(_request(0.0))
    assert resp.evidence.breakdown_dict["bb"] == 0.0


def test_bb_score_zero_at_moderate_squeeze():
    uc = ScoreForeignFlowUseCase()
    resp = uc.execute(_request(0.15))
    assert resp.evidence.breakdown_dict["bb"] == 0.0


def test_bb_score_zero_at_loose():
    uc = ScoreForeignFlowUseCase()
    resp = uc.execute(_request(0.50))
    assert resp.evidence.breakdown_dict["bb"] == 0.0


def test_bb_key_still_in_breakdown():
    uc = ScoreForeignFlowUseCase()
    resp = uc.execute(_request(0.0))
    assert "bb" in resp.evidence.breakdown_dict
    assert resp.evidence.breakdown_dict["bb"] == 0.0


def test_total_score_excludes_bb_contribution():
    uc = ScoreForeignFlowUseCase()
    tight = uc.execute(_request(0.0)).evidence.foreign_flow_score
    loose = uc.execute(_request(0.99)).evidence.foreign_flow_score
    assert tight == loose


def test_bb_can_be_re_enabled_via_explicit_policy():
    policy = ForeignFlowScorePolicy(
        bb_squeeze=BollingerSqueezePolicy(enabled=True, weight=10.0),
    )
    uc = ScoreForeignFlowUseCase(policy)
    resp = uc.execute(_request(0.0))
    assert resp.evidence.breakdown_dict["bb"] > 0.0
