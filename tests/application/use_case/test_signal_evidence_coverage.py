"""Coverage warning, breakdown, and response shape tests for signal evidence."""

import pytest

from tests.application.use_case.signal_evidence_fixtures import (
    _ctx,
    _flow_evidence,
    _req,
    _setup_evidence,
    _use_case,
)


def test_low_confidence_emits_coverage_warning():
    # Only flow evidence (confidence=0.40 < 0.50) → warning
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence()))
    assert resp.coverage_warning is not None
    assert "40%" in resp.coverage_warning


def test_full_confidence_no_coverage_warning():
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(),
    ))
    assert resp.coverage_warning is None


def test_setup_only_confidence_above_50_no_warning():
    # Only setup (confidence=0.60 >= 0.50) → no warning
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("MATCH")))
    assert resp.coverage_warning is None


def test_breakdown_includes_present_groups_and_confidence():
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.70),
    ))
    bd = resp.assessment.breakdown_dict
    assert "setup_quality_group" in bd
    assert "flow_confirmation_group" in bd
    assert "evidence_confidence" in bd
    assert bd["setup_quality_group"] == 100.0
    assert bd["flow_confirmation_group"] == pytest.approx(70.0)
    assert bd["evidence_confidence"] == pytest.approx(100.0)


def test_breakdown_omits_missing_groups():
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence()))
    bd = resp.assessment.breakdown_dict
    assert "setup_quality_group" not in bd
    assert "flow_confirmation_group" in bd


def test_flag_adjustment_in_breakdown_when_nonzero():
    uc = _use_case()
    ctx = _ctx(forward_pe=55.0)
    resp = uc.execute(_req(signal_context=ctx))
    bd = resp.assessment.breakdown_dict
    assert "flag_adjustment" in bd
    assert bd["flag_adjustment"] == -10.0


def test_no_flag_adjustment_in_breakdown_when_zero():
    uc = _use_case()
    resp = uc.execute(_req())
    bd = resp.assessment.breakdown_dict
    assert "flag_adjustment" not in bd


def test_response_has_all_phase4_fields():
    uc = _use_case()
    resp = uc.execute(_req())
    assert resp.evidence_confidence is not None
    assert isinstance(resp.active_flags, tuple)
    assert isinstance(resp.flag_adjustment, int)
    assert resp.raw_group_score is not None
