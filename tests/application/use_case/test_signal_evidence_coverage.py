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


def test_flow_only_is_complete_coverage_with_no_warning():
    # ADR-067: flow_confirmation is the only required PRODUCTION group, so a
    # flow-only request is COMPLETE, not incomplete. Before the retirement this
    # warned that setup_quality was absent — a warning about a group no
    # production surface ever attached. Asserted under the default ALL_REQUIRED
    # scope, because that is where the old warning came from.
    uc = _use_case()
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence()))
    assert resp.coverage_warning is None
    assert resp.signal_authority_coverage == pytest.approx(1.0)


def test_attached_required_flow_only_skips_absent_setup_warning():
    from src.domain.value_objects.evidence_source_availability import (
        AuthorityDenominatorScope,
    )

    uc = _use_case()
    resp = uc.execute(
        _req(
            flow_confirmation_evidence=_flow_evidence(),
            authority_denominator_scope=AuthorityDenominatorScope.ATTACHED_REQUIRED,
        )
    )
    assert resp.coverage_warning is None
    assert resp.signal_authority_coverage == pytest.approx(1.0)


def test_full_confidence_no_coverage_warning():
    uc = _use_case()
    resp = uc.execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(),
        )
    )
    assert resp.coverage_warning is None


def test_setup_only_reports_no_production_evidence_present():
    # ADR-067: setup is no longer a production evidence group, so a setup-only
    # request has no production evidence at all. The warning is the
    # "nothing present" form, not the per-group "flow_confirmation absent"
    # form — there is no attached production group to compare against.
    uc = _use_case()
    resp = uc.execute(_req(setup_evidence=_setup_evidence("MATCH")))
    assert resp.coverage_warning is not None
    assert "neutral prior only" in resp.coverage_warning
    assert resp.signal_authority_coverage == pytest.approx(0.0)


def test_breakdown_includes_present_groups_and_authority_coverage():
    uc = _use_case()
    resp = uc.execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.70),
        )
    )
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
    resp = uc.execute(
        _req(signal_context=ctx, flow_confirmation_evidence=_flow_evidence(capped_strength=0.50))
    )
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
    resp = uc.execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(),
            flow_all_authoritative=False,
        )
    )
    assert resp.coverage_warning is not None
    assert "flow_confirmation" in resp.coverage_warning
    assert "not source-authoritative" in resp.coverage_warning
    assert "required evidence absent" not in resp.coverage_warning


def test_attached_non_production_registration_names_the_group():
    # HIGH-2 distinction 2: evidence attached but its authority_registration
    # resolves to a non-PRODUCTION status (here: unknown -> DIAGNOSTIC).
    # Exercised on flow_confirmation now that ADR-067 left it the only
    # evidence group; the rule under test is unchanged.
    config = SignalEngineConfig(
        evidence_groups=EvidenceGroupsConfig(
            flow_confirmation=EvidenceGroupConfig(
                weight=0.40,
                authority_registration="not_a_registered_name",
                required_for_authority=True,
            ),
        )
    )
    uc = _use_case(config)
    resp = uc.execute(_req(flow_confirmation_evidence=_flow_evidence()))
    assert resp.coverage_warning is not None
    assert "flow_confirmation" in resp.coverage_warning
    assert "registration is not PRODUCTION" in resp.coverage_warning
    # A diagnostic registration never enters the authority denominator, so
    # with no PRODUCTION group left the coverage is 0.0, not 1.0.
    assert resp.signal_authority_coverage == pytest.approx(0.0)
