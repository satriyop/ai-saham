"""Alpha/trigger projection and setup phase/gate tests."""

import pytest

from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.services.signal_engine_config import (
    DecisionPolicyConfig,
    RegimeDecisionPolicyConfig,
    SignalEngineConfig,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from tests.application.use_case.signal_evidence_fixtures import (
    _company_quality,
    _flow_evidence,
    _phase_state,
    _req,
    _sector_context,
    _setup_evidence,
    _use_case,
)


def test_signal_authority_coverage_drives_decision_floor():
    # HIGH-2: there is one canonical signal_authority_coverage, computed by
    # SignalEvidenceGroupScorer from evidence presence/authority — not a
    # separate phase-level coverage/conviction pair.
    #
    # ADR-067: sub-floor coverage used to come for free from the absent
    # setup_quality group sitting in the ALL_REQUIRED denominator. With
    # flow_confirmation the sole production group, attached flow covers itself
    # completely, so the shortfall is now produced the way production produces
    # it — unresolved source availability (flow_all_authoritative=False).
    config = SignalEngineConfig(
        decision_policy=DecisionPolicyConfig(
            regime_policy={
                "RISK_ON": RegimeDecisionPolicyConfig(
                    enter_allowed=True,
                    max_decision="ENTER",
                    enter_threshold=70,
                    watch_threshold=45,
                    min_signal_authority_coverage=0.7,
                ),
                "NEUTRAL": RegimeDecisionPolicyConfig(),
                "RISK_OFF": RegimeDecisionPolicyConfig(enter_allowed=False, max_decision="WATCH"),
                "VOLATILE": RegimeDecisionPolicyConfig(enter_allowed=False, max_decision="WATCH"),
            }
        )
    )
    resp = _use_case(config).execute(
        _req(
            flow_confirmation_evidence=_flow_evidence(0.95),
            flow_all_authoritative=False,
            setup_family="foreign-bounce",
        )
    )

    assert resp.signal_authority_coverage == pytest.approx(0.0)
    assert resp.assessment.entry_quality.value == "WATCH"
    assert any(
        "ENTER requires signal_authority_coverage" in reason
        for reason in resp.assessment.decision_constraints.constraint_reasons
    )


@pytest.mark.parametrize(
    "setup_evidence_kwargs",
    [
        pytest.param(None, id="no_setup_evidence"),
        pytest.param(
            {
                "setup_name": "foreign-bounce",
                "setup_family": "accumulation",
                "entry_authority": True,
                "can_enter_from_phases": ("BREAKOUT_CONFIRMATION",),
            },
            id="would_once_have_resolved_ready",
        ),
        pytest.param(
            {
                "setup_name": "smart-money-confirmed",
                "setup_family": "confirmation",
                "entry_authority": False,
            },
            id="would_once_have_resolved_ineligible",
        ),
        pytest.param(
            {
                "setup_name": "foreign-bounce",
                "setup_family": "accumulation",
                "entry_authority": True,
                "can_enter_from_phases": ("COMPRESSION",),
            },
            id="would_once_have_failed_phase_membership",
        ),
    ],
)
def test_setup_evidence_has_no_route_to_the_action(setup_evidence_kwargs):
    """ADR-067 §4: setup evidence cannot reach Action through readiness.

    These four requests are identical apart from the ``SetupEvidence`` attached,
    and the three that carry one span the branches that used to decide the
    verdict outright — ``entry_authority``, ``can_enter_from_phases`` membership,
    and the READY path. Before this slice they produced ENTER, WATCH-via-
    INELIGIBLE and WATCH-via-INELIGIBLE respectively; the readiness evaluator
    no longer accepts the input, so all four must now agree exactly. A future
    change that re-opens the side door fails here rather than silently restoring
    setup evidence's veto.
    """
    baseline = _use_case().execute(
        _req(
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="foreign-bounce",
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )
    resp = _use_case().execute(
        _req(
            setup_evidence=(
                _setup_evidence("MATCH", **setup_evidence_kwargs)
                if setup_evidence_kwargs is not None
                else None
            ),
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="foreign-bounce",
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )

    assert resp.assessment.entry_quality == baseline.assessment.entry_quality
    assert (
        resp.assessment.decision_constraints.max_decision
        == baseline.assessment.decision_constraints.max_decision
    )
    assert (
        resp.assessment.decision_constraints.constraint_reasons
        == baseline.assessment.decision_constraints.constraint_reasons
    )
    assert resp.setup_readiness == baseline.setup_readiness


def test_setup_family_without_a_match_still_caps_enter_to_watch():
    """The surviving cap: a named family whose match is not evaluated on this
    path resolves UNAVAILABLE, and UNAVAILABLE still caps ENTER to WATCH."""
    resp = _use_case().execute(
        _req(
            flow_confirmation_evidence=_flow_evidence(0.95),
            setup_family="foreign-bounce",
            setup_phase=None,
        )
    )

    assert resp.assessment.entry_quality.value == "WATCH"
    assert any(
        "Setup readiness UNAVAILABLE" in reason
        for reason in resp.assessment.decision_constraints.constraint_reasons
    )


def test_alpha_trigger_projection_uses_existing_group_scores():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.horizon == "SWING_10D"
    assert at.alpha_score == pytest.approx(50.0)
    assert at.trigger_score == pytest.approx(92.6829268293)
    assert at.final_exact_score == pytest.approx(75.6097560976)
    assert at.coverage == pytest.approx(0.65)
    assert at.authority_coverage == pytest.approx(0.65)
    assert {c.group for c in at.group_contributions} == {
        "setup_quality",
        "institutional_flow",
        "sector_context",
        "company_quality_context",
    }
    assert "sector_context:missing" in at.unavailable_reasons
    assert "company_quality_context:missing" in at.unavailable_reasons
    # ADR-067 boundary check: every Alpha/Trigger number above is unchanged by
    # the retirement — the Alpha/Trigger `setup_quality` slot is a separate
    # diagnostic projection with its own group_weights and route_fractions, and
    # it still reads setup_group_score. Only the canonical score moved, from
    # the old 100/50 blend to the flow group score alone.
    assert resp.assessment.score == 50
    assert resp.assessment.raw_exact_score == pytest.approx(50.0)
    final_score = resp.assessment.to_dict()["alpha_trigger_score"]["final_exact_score"]
    assert final_score == pytest.approx(75.6098)


def test_alpha_trigger_sector_context_feeds_sector_context_slot_as_diagnostic_coverage():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            sector_context_evidence=_sector_context("BULLISH"),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.coverage == pytest.approx(0.90)
    assert at.authority_coverage == pytest.approx(0.65)
    assert at.alpha_score == pytest.approx(50.0)
    assert at.trigger_score == pytest.approx(92.6829268293)
    market = [c for c in at.group_contributions if c.group == "sector_context"][0]
    assert market.present is True
    assert market.score == pytest.approx(75.0)
    assert market.effective_weight == pytest.approx(0.0)
    assert "diagnostic_report_only" in market.reasons


@pytest.mark.parametrize(
    "regime,expected_score",
    [("BULLISH", 75.0), ("NEUTRAL", 50.0), ("BEARISH", 25.0)],
)
def test_sector_context_regime_maps_to_exact_slot_score(regime, expected_score):
    """SECTOR-CONTEXT-IDENTITY score mapping is fixed and identity-only —
    the numbers are unchanged from the pre-removal market_context slot."""
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            sector_context_evidence=_sector_context(regime),
        )
    )
    at = resp.alpha_trigger_score
    contribution = [c for c in at.group_contributions if c.group == "sector_context"][0]
    assert contribution.present is True
    assert contribution.score == pytest.approx(expected_score)


def test_sector_context_unknown_regime_is_absent_from_scoring():
    """UNKNOWN sector regime is not a present contribution: score 0.0 and the
    slot is reported missing per the current presence contract."""
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            sector_context_evidence=_sector_context("UNKNOWN"),
        )
    )
    at = resp.alpha_trigger_score
    contribution = [c for c in at.group_contributions if c.group == "sector_context"][0]
    assert contribution.present is False
    assert contribution.score == pytest.approx(0.0)
    assert "sector_context:missing" in at.unavailable_reasons


def test_genuine_market_context_does_not_create_sector_context_contribution():
    """Genuine market-wide MarketContext (regime conditioning) must never
    populate the Alpha/Trigger sector_context slot, and no group is ever named
    'market_context'. Only SectorContextEvidence populates sector_context."""
    from src.domain.value_objects.market_context import MarketContext, MarketRegime
    from tests.application.use_case.signal_evidence_fixtures import SNAP

    genuine_market_context = MarketContext(
        regime=MarketRegime("RISK_ON"),
        conviction=0.7,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=SNAP,
    )

    # 1-4: genuine MarketContext supplied, no SectorContextEvidence.
    resp_without = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            market_context=genuine_market_context,
            sector_context_evidence=None,
        )
    )
    groups_without = {c.group for c in resp_without.alpha_trigger_score.group_contributions}
    assert "market_context" not in groups_without
    sector_without = [
        c
        for c in resp_without.alpha_trigger_score.group_contributions
        if c.group == "sector_context"
    ][0]
    assert sector_without.present is False

    # 5-6: only once SectorContextEvidence is supplied is sector_context present.
    resp_with = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            market_context=genuine_market_context,
            sector_context_evidence=_sector_context("BULLISH"),
        )
    )
    groups_with = {c.group for c in resp_with.alpha_trigger_score.group_contributions}
    assert "market_context" not in groups_with
    sector_with = [
        c for c in resp_with.alpha_trigger_score.group_contributions if c.group == "sector_context"
    ][0]
    assert sector_with.present is True


def test_alpha_trigger_company_quality_feeds_slot_as_diagnostic_coverage():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            company_quality_context_evidence=_company_quality(72.0),
        )
    )

    at = resp.alpha_trigger_score
    assert at is not None
    cq = [c for c in at.group_contributions if c.group == "company_quality_context"][0]
    assert cq.present is True
    assert cq.score == pytest.approx(72.0)
    assert cq.effective_weight == pytest.approx(0.0)
    assert "diagnostic_report_only" in cq.reasons
    assert cq.alpha_fraction == pytest.approx(1.0)


def test_company_quality_slot_has_zero_scoring_authority():
    """DIAGNOSTIC proof: a real company_quality score must NOT move final score."""
    common = dict(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
        setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
    )
    empty = _use_case().execute(_req(**common))
    filled = _use_case().execute(
        _req(
            **common,
            company_quality_context_evidence=_company_quality(88.0),
        )
    )

    assert filled.alpha_trigger_score.final_exact_score == pytest.approx(
        empty.alpha_trigger_score.final_exact_score
    )
    assert filled.alpha_trigger_score.alpha_score == pytest.approx(
        empty.alpha_trigger_score.alpha_score
    )
    assert filled.assessment.score == empty.assessment.score
    cq = [
        c
        for c in filled.alpha_trigger_score.group_contributions
        if c.group == "company_quality_context"
    ][0]
    assert cq.present is True
    assert cq.effective_weight == pytest.approx(0.0)


def test_alpha_trigger_missing_groups_do_not_neutral_fill_side_denominators():
    resp = _use_case().execute(_req(setup_evidence=_setup_evidence("MATCH")))

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.alpha_score is None
    assert at.trigger_score == pytest.approx(100.0)
    assert at.final_exact_score == pytest.approx(100.0)
    assert at.coverage == pytest.approx(0.35)
    assert at.authority_coverage == pytest.approx(0.35)
    assert "institutional_flow:missing" in at.unavailable_reasons
    assert "sector_context:missing" in at.unavailable_reasons
    assert "company_quality_context:missing" in at.unavailable_reasons
    assert "alpha:no_production_weight" in at.unavailable_reasons


def test_flow_does_not_contribute_to_trigger_without_price_volume_confirmation():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.COMPRESSION),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.flow_trigger_allowed is False
    assert at.alpha_score == pytest.approx(50.0)
    assert at.trigger_score == pytest.approx(100.0)
    flow = [c for c in at.group_contributions if c.group == "institutional_flow"][0]
    assert flow.trigger_allowed is False
    assert "flow_trigger_blocked:setup_phase_not_breakout_confirmation" in flow.reasons


def test_breakout_confirmation_with_confirmed_flow_unlocks_flow_trigger_contribution():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(
                capped_strength=0.50,
                confirmation_status="CONFIRMED",
            ),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.flow_trigger_allowed is True
    assert at.trigger_score == pytest.approx(92.6829268293)


def test_flow_still_blocked_when_breakout_phase_lacks_confirmed_flow():
    resp = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(
                capped_strength=0.50,
                confirmation_status="WATCH_ZONE",
            ),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
        )
    )

    at = resp.alpha_trigger_score

    assert at is not None
    assert at.flow_trigger_allowed is False
    assert at.trigger_score == pytest.approx(100.0)
    assert "flow_trigger_blocked:flow_not_confirmed" in at.reasons
    assert resp.signal_authority_coverage == pytest.approx(1.0)
    assert resp.coverage_warning is None


def test_diagnostic_producers_zero_authority():
    """Verify that strategy, institutional accumulation, and ticker profile diagnostic
    producers are not accepted by AssessSignalEvidenceRequest, and that sector context
    and company quality context are diagnostic-only (zero effective weight).
    """

    fields = [f.name for f in AssessSignalEvidenceRequest.__dataclass_fields__.values()]
    assert "strategy_evidence" not in fields
    assert "institutional_accumulation_evidence" not in fields
    assert "ticker_profile_snapshot" not in fields

    uc = _use_case()
    common = dict(
        setup_evidence=_setup_evidence("MATCH"),
        flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
        setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
    )
    empty = uc.execute(_req(**common))
    filled = uc.execute(
        _req(
            **common,
            sector_context_evidence=_sector_context("BULLISH"),
            company_quality_context_evidence=_company_quality(88.0),
        )
    )

    assert filled.alpha_trigger_score.final_exact_score == pytest.approx(
        empty.alpha_trigger_score.final_exact_score
    )
    assert filled.assessment.score == empty.assessment.score
    market = [
        c for c in filled.alpha_trigger_score.group_contributions if c.group == "sector_context"
    ][0]
    cq = [
        c
        for c in filled.alpha_trigger_score.group_contributions
        if c.group == "company_quality_context"
    ][0]
    assert market.effective_weight == pytest.approx(0.0)
    assert cq.effective_weight == pytest.approx(0.0)
