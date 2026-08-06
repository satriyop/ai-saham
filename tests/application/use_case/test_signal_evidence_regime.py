"""Market regime and canonical score regression tests for signal evidence."""

import pytest

from tests.application.use_case.signal_evidence_fixtures import (
    _flow_evidence,
    _market_ctx,
    _req,
    _setup_evidence,
    _use_case,
)


@pytest.mark.parametrize("regime", ["RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE"])
def test_canonical_score_is_identical_across_regimes(regime):
    """assessment.score must be regime-neutral regardless of _condition_group_scores output."""
    uc = _use_case()
    resp_no_ctx = uc.execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(0.70),
        )
    )
    resp_with_ctx = uc.execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(0.70),
            market_context=_market_ctx(regime),
        )
    )
    # Canonical score must be the same regardless of which regime was passed
    assert resp_with_ctx.assessment.score == resp_no_ctx.assessment.score, (
        f"assessment.score changed under regime={regime}: "
        f"{resp_no_ctx.assessment.score} → {resp_with_ctx.assessment.score}. "
        "Regime must not mutate canonical score (ADR-024 TD-1)."
    )


def test_legacy_conditioned_score_may_differ_from_canonical():
    """legacy_conditioned_score is diagnostic only and is allowed to differ from canonical."""
    uc = _use_case()
    # ADR-067: the RISK_OFF weak-setup discount can no longer move any score,
    # because setup is not in the evidence basis. The NEUTRAL weak-flow
    # discount still can, so the divergence this test is about is exercised
    # through flow: score=40 < weak_flow_threshold=50 → legacy ×0.80.
    resp = uc.execute(
        _req(
            flow_confirmation_evidence=_flow_evidence(0.40),
            market_context=_market_ctx("NEUTRAL"),
        )
    )
    # Canonical score is unaffected by regime
    resp_no_ctx = uc.execute(_req(flow_confirmation_evidence=_flow_evidence(0.40)))
    assert resp.assessment.score == resp_no_ctx.assessment.score
    assert resp.assessment.legacy_conditioned_score < resp.assessment.score
