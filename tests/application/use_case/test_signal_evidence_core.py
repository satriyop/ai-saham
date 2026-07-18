"""Core signal evidence tests for AssessSignalEvidenceUseCase."""

import pytest

from src.application.use_case.assess_signal_use_case import (
    EvidenceGroupConfig,
    EvidenceGroupsConfig,
    SignalEngineConfig,
)
from src.domain.value_objects.signal_assessment import SignalStrength
from tests.application.use_case.signal_evidence_fixtures import (
    _flow_evidence,
    _req,
    _setup_evidence,
    _use_case,
)


def test_both_groups_missing_returns_neutral_prior():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.assessment.score == 50
    assert resp.signal_authority_coverage == 0.0
    assert resp.raw_exact_score == 50


def test_both_groups_missing_strength_is_moderate():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.assessment.strength == SignalStrength.MODERATE


def test_both_groups_missing_coverage_warning_present():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.coverage_warning is not None
    assert "No evidence groups present" in resp.coverage_warning


def test_both_groups_missing_no_flags_score_stays_50():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.active_flags == ()
    assert resp.flag_adjustment == 0
    assert resp.assessment.score == 50


def test_only_flow_evidence_renormalized_to_flow_score():
    # capped_strength=0.80 → flow group score = 80.0
    # Only flow (weight=0.40) present → renormalized score = 80.0
    # HIGH-2 Finding 1: a bare SignalEngineConfig() now carries the canonical
    # RISK_ON/NEUTRAL 0.70 min_signal_authority_coverage floor (matching
    # config/signal_engine.yaml), not the old dataclass default of 0.0.
    # _classify_entry itself still gates on directional strength only, so
    # the raw STRONG score alone would classify ENTER — but
    # DecisionPolicyService (always applied by the full use case) now caps
    # this single-group 0.40 coverage below the 0.70 floor to WATCH.
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence(capped_strength=0.80)))
    assert resp.assessment.score == 80
    assert resp.assessment.entry_quality.name == "WATCH"
    # signal_authority_coverage = 0.40 / (0.60+0.40) = 0.40
    assert resp.signal_authority_coverage == pytest.approx(0.40)
    assert resp.assessment.signal_authority_coverage == pytest.approx(0.40)


def test_only_setup_evidence_renormalized_to_setup_score():
    # MATCH → match_strength=100.0; only setup (weight=0.60) present → score=100
    # HIGH-2 Finding 1: coverage 0.60 is below the default 0.70 floor, so
    # DecisionPolicyService caps the raw STRONG/ENTER classification to WATCH.
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("MATCH")))
    assert resp.assessment.score == 100
    assert resp.assessment.entry_quality.name == "WATCH"
    # signal_authority_coverage = 0.60 / 1.0 = 0.60
    assert resp.signal_authority_coverage == pytest.approx(0.60)
    assert resp.assessment.signal_authority_coverage == pytest.approx(0.60)


def test_partial_setup_match_gives_lower_score():
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("PARTIAL")))
    assert resp.assessment.score == 60   # match_strength=60.0


def test_no_match_setup_gives_low_score():
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("NO_MATCH")))
    assert resp.assessment.score == 20   # match_strength=20.0


def test_both_groups_present_weighted_combination():
    # setup=MATCH (100.0, weight=0.60) + flow=0.50 capped (50.0, weight=0.40)
    # base_score = (100*0.60 + 50*0.40) / (0.60+0.40) = (60+20)/1.0 = 80.0
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
    ))
    assert resp.assessment.score == 80


def test_both_groups_present_full_strength_scores_100():
    # setup=MATCH (100) + flow capped=1.0 (100) → score=100
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=1.0),
    ))
    assert resp.assessment.score == 100
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.entry_quality.name == "ENTER"
    assert resp.assessment.signal_authority_coverage == pytest.approx(1.0)


def test_custom_group_weights_affect_score():
    # Custom: setup=0.80, flow=0.20
    cfg = SignalEngineConfig(
        evidence_groups=EvidenceGroupsConfig(
            setup_quality=EvidenceGroupConfig(weight=0.80),
            flow_confirmation=EvidenceGroupConfig(weight=0.20),
        )
    )
    uc = _use_case(cfg)
    # setup=PARTIAL (60), flow=capped=1.0 (100)
    # score = (60*0.80 + 100*0.20) / 1.0 = (48+20) = 68
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("PARTIAL"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=1.0),
    ))
    assert resp.assessment.score == 68


def test_strong_setup_only_score_capped_by_default_authority_coverage_floor():
    # HIGH-2 Finding 1: _classify_entry itself still gates on directional
    # strength only — a STRONG score alone classifies raw ENTER even though
    # only one evidence group (weight 0.60) is present. But
    # DecisionPolicyService is always applied downstream by the full use
    # case, and a bare SignalEngineConfig() now carries the canonical 0.70
    # min_signal_authority_coverage floor (matching config/signal_engine.yaml)
    # instead of the old dataclass default of 0.0 — so single-group 0.60
    # coverage below that floor caps the final decision to WATCH.
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("MATCH")))
    assert resp.assessment.score == 100
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.signal_authority_coverage == pytest.approx(0.60)
    assert resp.assessment.entry_quality.name == "WATCH"
