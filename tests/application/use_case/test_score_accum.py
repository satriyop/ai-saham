from datetime import date

from src.application.use_case.score_accum_use_case import (
    BollingerSqueezePolicy,
    EvidenceComponentPolicy,
    AccumScorePolicy,
    ScoreAccumRequest,
    ScoreAccumUseCase,
)
from src.domain.value_objects.accum_score_breakdown import (
    ForeignFlowComponentStatus,
)


def _full_request(**overrides):
    base = dict(
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
    base.update(overrides)
    return ScoreAccumRequest(**base)


def test_score_accum_matches_legacy_breakdown_shape():
    uc = ScoreAccumUseCase()

    resp = uc.execute(_full_request())

    evidence = resp.evidence
    # Rescaled 0-120 -> 0-100 (ADR-039). bb_squeeze is disabled by default.
    assert evidence.accum_score == 94.9
    assert evidence.breakdown_dict == {
        "cons": 33.3,
        "streak": 15.8,
        "vwap": 16.7,
        "rsi": 8.3,
        "flow": 8.3,
        "bb": None,  # DISABLED — not zero
        "inst": 12.5,
    }
    assert evidence.component("bb").status is ForeignFlowComponentStatus.DISABLED
    assert evidence.component_coverage == 1.0
    assert evidence.missing_components == ()


def test_score_accum_can_disable_component():
    policy = AccumScorePolicy(
        consistency=EvidenceComponentPolicy(enabled=False, weight=33.3),
    )
    uc = ScoreAccumUseCase(policy)

    resp = uc.execute(
        _full_request(
            consecutive_streak=0,
            vwap_discount_pct=0.0,
            rsi=None,
            avg_flow_ratio=0.0,
            bb_width_pctile=None,
            bci_label=None,
        )
    )

    assert resp.evidence.component("cons").status is ForeignFlowComponentStatus.DISABLED
    assert resp.evidence.breakdown_dict["cons"] is None
    # streak 0 available, vwap 0 available, rsi missing, flow 0 available,
    # bb disabled, inst missing → score = 0.0
    assert resp.evidence.accum_score == 0.0
    assert "rsi" in resp.evidence.missing_components
    assert "inst" in resp.evidence.missing_components


def test_missing_vwap_and_real_zero_vwap_serialize_differently():
    uc = ScoreAccumUseCase()
    missing = uc.execute(_full_request(vwap_discount_pct=None)).evidence
    zero = uc.execute(_full_request(vwap_discount_pct=0.0)).evidence

    assert missing.component("vwap").status is ForeignFlowComponentStatus.MISSING
    assert missing.breakdown_dict["vwap"] is None
    assert zero.component("vwap").status is ForeignFlowComponentStatus.AVAILABLE
    assert zero.breakdown_dict["vwap"] == 0.0
    assert missing.to_dict()["components"] != zero.to_dict()["components"]
    assert missing.accum_score < zero.accum_score + 16.7  # missing contributes 0
    assert missing.accum_score == round(zero.accum_score - 0.0, 1)


def test_missing_flow_ratio_and_real_zero_flow_ratio_serialize_differently():
    uc = ScoreAccumUseCase()
    missing = uc.execute(_full_request(avg_flow_ratio=None)).evidence
    zero = uc.execute(_full_request(avg_flow_ratio=0.0)).evidence

    assert missing.component("flow").status is ForeignFlowComponentStatus.MISSING
    assert missing.breakdown_dict["flow"] is None
    assert zero.component("flow").status is ForeignFlowComponentStatus.AVAILABLE
    assert zero.breakdown_dict["flow"] == 0.0
    assert missing.to_dict()["missing_components"] == ["flow"]
    assert zero.to_dict()["missing_components"] == []


def test_missing_rsi_receives_no_points():
    uc = ScoreAccumUseCase()
    present = uc.execute(_full_request(rsi=40.0)).evidence
    missing = uc.execute(_full_request(rsi=None)).evidence

    assert present.breakdown_dict["rsi"] == 8.3
    assert missing.breakdown_dict["rsi"] is None
    assert missing.component("rsi").status is ForeignFlowComponentStatus.MISSING
    assert missing.accum_score == round(present.accum_score - 8.3, 1)


def test_disabled_bb_is_distinct_from_missing_bb():
    disabled_uc = ScoreAccumUseCase()  # default bb disabled
    enabled_uc = ScoreAccumUseCase(
        AccumScorePolicy(
            bb_squeeze=BollingerSqueezePolicy(enabled=True, weight=8.3),
        )
    )
    disabled = disabled_uc.execute(_full_request(bb_width_pctile=None)).evidence
    missing = enabled_uc.execute(_full_request(bb_width_pctile=None)).evidence

    assert disabled.component("bb").status is ForeignFlowComponentStatus.DISABLED
    assert missing.component("bb").status is ForeignFlowComponentStatus.MISSING
    assert disabled.breakdown_dict["bb"] is None
    assert missing.breakdown_dict["bb"] is None
    assert "bb" not in disabled.missing_components
    assert "bb" in missing.missing_components


def test_missing_bci_is_distinct_from_retail_led():
    uc = ScoreAccumUseCase()
    missing = uc.execute(_full_request(bci_label=None)).evidence
    retail = uc.execute(_full_request(bci_label="RETAIL-LED", bci_tier1_count=0)).evidence

    assert missing.component("inst").status is ForeignFlowComponentStatus.MISSING
    assert missing.breakdown_dict["inst"] is None
    assert retail.component("inst").status is ForeignFlowComponentStatus.AVAILABLE
    assert retail.breakdown_dict["inst"] == 0.0
    assert missing.accum_score == retail.accum_score  # both 0 points
    assert missing.to_dict()["components"] != retail.to_dict()["components"]


def test_all_input_present_known_score_vector_unchanged():
    uc = ScoreAccumUseCase()
    evidence = uc.execute(_full_request()).evidence
    assert evidence.accum_score == 94.9
    assert {
        k: v
        for k, v in evidence.breakdown_dict.items()
        if k != "bb"
    } == {
        "cons": 33.3,
        "streak": 15.8,
        "vwap": 16.7,
        "rsi": 8.3,
        "flow": 8.3,
        "inst": 12.5,
    }
