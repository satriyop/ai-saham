from datetime import date

from src.application.use_case.score_accum_use_case import (
    BollingerSqueezePolicy,
    AccumScorePolicy,
    ScoreAccumRequest,
    ScoreAccumUseCase,
)
from src.domain.value_objects.accum_score_breakdown import (
    ForeignFlowComponentStatus,
)


def _request(bb_width_pctile):
    return ScoreAccumRequest(
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


def test_bb_disabled_by_default_is_not_zero_points():
    uc = ScoreAccumUseCase()
    resp = uc.execute(_request(0.0))
    assert resp.evidence.component("bb").status is ForeignFlowComponentStatus.DISABLED
    assert resp.evidence.breakdown_dict["bb"] is None


def test_bb_disabled_at_moderate_squeeze():
    uc = ScoreAccumUseCase()
    resp = uc.execute(_request(0.15))
    assert resp.evidence.breakdown_dict["bb"] is None


def test_bb_disabled_at_loose():
    uc = ScoreAccumUseCase()
    resp = uc.execute(_request(0.50))
    assert resp.evidence.breakdown_dict["bb"] is None


def test_bb_key_still_in_breakdown_as_disabled():
    uc = ScoreAccumUseCase()
    resp = uc.execute(_request(0.0))
    assert "bb" in resp.evidence.breakdown_dict
    assert resp.evidence.component("bb").status is ForeignFlowComponentStatus.DISABLED


def test_total_score_excludes_bb_contribution():
    uc = ScoreAccumUseCase()
    tight = uc.execute(_request(0.0)).evidence.accum_score
    loose = uc.execute(_request(0.99)).evidence.accum_score
    assert tight == loose


def test_bb_can_be_re_enabled_via_explicit_policy():
    policy = AccumScorePolicy(
        bb_squeeze=BollingerSqueezePolicy(enabled=True, weight=10.0),
    )
    uc = ScoreAccumUseCase(policy)
    resp = uc.execute(_request(0.0))
    assert resp.evidence.component("bb").status is ForeignFlowComponentStatus.AVAILABLE
    assert resp.evidence.breakdown_dict["bb"] > 0.0


def test_bb_disabled_with_live_loaded_config_at_maximum_squeeze():
    """Regression guard: the shipped config/accumulation_screener.yaml must
    not re-enable bb_squeeze scoring. bb_width_pctile stays populated for
    setup-phase diagnostics; only the score contribution is disabled."""
    from src.infrastructure.config.accumulation_screener_config import (
        load_accumulation_screener_config,
    )

    loaded_policy = load_accumulation_screener_config().accum_score_policy
    uc = ScoreAccumUseCase(loaded_policy)
    resp = uc.execute(_request(0.0))

    assert resp.evidence.component("bb").status is ForeignFlowComponentStatus.DISABLED
    assert resp.evidence.breakdown_dict["bb"] is None
    assert resp.evidence.bb_width_pctile == 0.0
