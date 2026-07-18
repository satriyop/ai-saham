"""Coverage warning, breakdown, and response shape tests for signal evidence."""

import pytest

from src.application.services.signal_engine_config import (
    EvidenceGroupConfig,
    EvidenceGroupsConfig,
    SignalEngineConfig,
)
from tests.application.use_case.signal_evidence_fixtures import (
    _ctx,
    _flow_evidence,
    _req,
    _setup_evidence,
    _use_case,
)


def test_flow_only_emits_coverage_warning_naming_absent_setup_group():
    # HIGH-2: only flow evidence attached -> setup_quality is a required
    # PRODUCTION group that is absent; the warning must name it and must not
    # use the phrase "evidence confidence".
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence()))
    assert resp.coverage_warning is not None
    assert "setup_quality" in resp.coverage_warning
    assert "required evidence absent" in resp.coverage_warning
    assert "evidence confidence" not in resp.coverage_warning.lower()
    assert "conviction" not in resp.coverage_warning.lower()


def test_full_confidence_no_coverage_warning():
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(),
    ))
    assert resp.coverage_warning is None


def test_setup_only_emits_coverage_warning_naming_absent_flow_group():
    # HIGH-2: only setup evidence attached -> flow_confirmation (required
    # PRODUCTION group) is absent and must be named — this is a genuine
    # incompleteness the old 0.5-ratio heuristic silently hid.
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("MATCH")))
    assert resp.coverage_warning is not None
    assert "flow_confirmation" in resp.coverage_warning
    assert "required evidence absent" in resp.coverage_warning


def test_breakdown_includes_present_groups_and_authority_coverage():
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.70),
    ))
    bd = resp.assessment.breakdown_dict
    assert "setup_quality_group" in bd
    assert "flow_confirmation_group" in bd
    assert "signal_authority_coverage" in bd
    assert bd["setup_quality_group"] == 100.0
    assert bd["flow_confirmation_group"] == pytest.approx(70.0)
    assert bd["signal_authority_coverage"] == pytest.approx(100.0)


def test_breakdown_omits_missing_groups():
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence()))
    bd = resp.assessment.breakdown_dict
    assert "setup_quality_group" not in bd
    assert "flow_confirmation_group" in bd


def test_flag_adjustment_in_breakdown_when_nonzero():
    uc = _use_case()
    ctx = _ctx(forward_pe=55.0)
    resp = uc.execute(_req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    bd = resp.assessment.breakdown_dict
    assert "flag_adjustment" in bd
    assert bd["flag_adjustment"] == -10.0


def test_no_flag_adjustment_in_breakdown_when_zero():
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    bd = resp.assessment.breakdown_dict
    assert "flag_adjustment" not in bd


def test_response_has_all_phase4_fields():
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence(capped_strength=0.50)))
    assert resp.signal_authority_coverage is not None
    assert isinstance(resp.active_flags, tuple)
    assert isinstance(resp.flag_adjustment, int)
    assert resp.raw_group_score is not None


def test_no_evidence_at_all_raises_no_production_signal_evidence_error():
    from src.application.exceptions import NoProductionSignalEvidenceError
    uc = _use_case()
    with pytest.raises(NoProductionSignalEvidenceError):
        uc.execute(_req())


def test_present_but_non_authoritative_flow_names_the_group():
    # HIGH-2 distinction 3: attached + PRODUCTION-registered, but the
    # resolved source availability is not authoritative.
    uc = _use_case()
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(),
        flow_all_authoritative=False,
    ))
    assert resp.coverage_warning is not None
    assert "flow_confirmation" in resp.coverage_warning
    assert "not source-authoritative" in resp.coverage_warning
    assert "required evidence absent" not in resp.coverage_warning


def test_attached_non_production_registration_names_the_group():
    # HIGH-2 distinction 2: evidence attached but its authority_registration
    # resolves to a non-PRODUCTION status (here: unknown -> DIAGNOSTIC).
    config = SignalEngineConfig(
        evidence_groups=EvidenceGroupsConfig(
            setup_quality=EvidenceGroupConfig(
                weight=0.60,
                authority_registration="not_a_registered_name",
                required_for_authority=True,
            ),
        )
    )
    uc = _use_case(config)
    resp = uc.execute(_req(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(),
    ))
    assert resp.coverage_warning is not None
    assert "setup_quality" in resp.coverage_warning
    assert "registration is not PRODUCTION" in resp.coverage_warning
    # setup_quality is diagnostic here, so it cannot lower authority coverage —
    # flow_confirmation alone (weight 0.40, required) fully covers itself.
    assert resp.signal_authority_coverage == pytest.approx(1.0)
