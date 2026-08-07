"""Tests for DailySetupLensImpactUseCase (bounded, read-only setup-lens impact)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.use_case.daily_setup_lens_impact_use_case import (
    DailySetupLensImpactCandidate,
    DailySetupLensImpactRequest,
    DailySetupLensImpactUseCase,
    SwingLensRequestDefaults,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
)
from src.application.use_case.plan_swing_workflow_use_case import (
    PlanSwingDataUnavailable,
)

DEFAULTS = SwingLensRequestDefaults(
    window=200,
    flow_window=20,
    risk_pct=1.0,
    atr_mult=2.0,
    rr=2.0,
    db_path=Path("/tmp/does-not-exist.db"),
)


class FakeWorkflow:
    """Scriptable stand-in for PlanSwingWorkflowUseCase.

    Records every request passed to execute(); returns a canned response object
    (or raises a scripted exception).
    """

    def __init__(self, response=None, exc: Exception | None = None):
        self._response = response
        self._exc = exc
        self.received_requests: list = []

    def execute(self, request):
        self.received_requests.append(request)
        if self._exc is not None:
            raise self._exc
        return self._response


def _response(
    *,
    action: str | None = "WATCH",
    signal_score: int = 70,
    match: str = "MATCH",
    entry_authority: bool = True,
    constraint_reasons: tuple[str, ...] = (),
):
    trade_setup = (
        SimpleNamespace(action=SimpleNamespace(value=action), signal_score=signal_score)
        if action is not None
        else None
    )
    signal_assessment = SimpleNamespace(
        assessment=SimpleNamespace(
            score=signal_score,
            decision_constraints=SimpleNamespace(constraint_reasons=constraint_reasons),
        )
    )
    setup_eval = SimpleNamespace(
        match=SimpleNamespace(value=match),
        entry_authority=entry_authority,
    )
    return SimpleNamespace(
        trade_setup=trade_setup,
        signal_assessment=signal_assessment,
        setup_eval=setup_eval,
    )


def _all_workflows(response=None, exc=None):
    return {name: FakeWorkflow(response=response, exc=exc) for name in AVAILABLE_SWING_SETUPS}


def test_empty_candidates_returns_empty_and_never_executes():
    workflows = _all_workflows(response=_response())
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    result = uc.execute(DailySetupLensImpactRequest(candidates=(), as_of_date=date(2026, 7, 1)))

    assert result.rows == ()
    for wf in workflows.values():
        assert wf.received_requests == []


def test_every_setup_represented_per_ticker():
    workflows = _all_workflows(response=_response())
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    result = uc.execute(
        DailySetupLensImpactRequest(
            candidates=(
                DailySetupLensImpactCandidate(ticker="BBRI", base_action="WATCH"),
                DailySetupLensImpactCandidate(ticker="BBCA", base_action="ENTER"),
            ),
            as_of_date=date(2026, 7, 1),
        )
    )

    assert len(result.rows) == 2
    for row in result.rows:
        assert len(row.cells) == len(AVAILABLE_SWING_SETUPS)
        assert {c.setup_name for c in row.cells} == set(AVAILABLE_SWING_SETUPS)
    assert result.rows[0].ticker == "BBRI"
    assert result.rows[0].base_action == "WATCH"


def test_match_partial_no_match_surfaced_per_setup():
    setups = list(AVAILABLE_SWING_SETUPS)
    workflows = {
        setups[0]: FakeWorkflow(response=_response(match="MATCH")),
        setups[1]: FakeWorkflow(response=_response(match="PARTIAL")),
        setups[2]: FakeWorkflow(response=_response(match="NO_MATCH")),
        setups[3]: FakeWorkflow(response=_response(match="MATCH")),
    }
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    result = uc.execute(
        DailySetupLensImpactRequest(
            candidates=(DailySetupLensImpactCandidate(ticker="BBRI", base_action="WATCH"),),
            as_of_date=date(2026, 7, 1),
        )
    )

    by_setup = {c.setup_name: c for c in result.rows[0].cells}
    assert by_setup[setups[0]].setup_match == "MATCH"
    assert by_setup[setups[1]].setup_match == "PARTIAL"
    assert by_setup[setups[2]].setup_match == "NO_MATCH"


def test_confirmation_only_setup_caps_action_and_populates_reason():
    reason = "smart_money_confirmed has no standalone entry authority for ENTER"
    workflows = _all_workflows(
        response=_response(
            action="WATCH",
            match="MATCH",
            entry_authority=False,
            constraint_reasons=(reason,),
        )
    )
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    result = uc.execute(
        DailySetupLensImpactRequest(
            candidates=(DailySetupLensImpactCandidate(ticker="INDF", base_action="WATCH"),),
            as_of_date=date(2026, 7, 1),
        )
    )

    cell = result.rows[0].cells[0]
    # Final action reflects the capped WATCH from TradeSetup, not an invented ENTER.
    assert cell.action == "WATCH"
    assert cell.entry_authority is False
    assert cell.capped_reason == reason


def test_phase_gated_setup_caps_action_with_reason():
    reason = "requires phase BREAKOUT_CONFIRMATION for ENTER"
    workflows = _all_workflows(
        response=_response(
            action="WATCH",
            match="MATCH",
            entry_authority=True,
            constraint_reasons=(reason,),
        )
    )
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    result = uc.execute(
        DailySetupLensImpactRequest(
            candidates=(DailySetupLensImpactCandidate(ticker="INDF", base_action="WATCH"),),
            as_of_date=date(2026, 7, 1),
        )
    )

    cell = result.rows[0].cells[0]
    assert cell.action == "WATCH"
    assert cell.capped_reason == reason


def test_generic_decision_constraint_does_not_become_no_entry_cap():
    # A generic score-floor reason must NOT surface as a capped_reason: only
    # setup entry-authority / phase-gate reasons justify a ``(no-entry)`` label.
    workflows = _all_workflows(
        response=_response(
            action="WATCH",
            match="MATCH",
            entry_authority=True,
            constraint_reasons=("RISK_ON ENTER requires score >= 70",),
        )
    )
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    result = uc.execute(
        DailySetupLensImpactRequest(
            candidates=(DailySetupLensImpactCandidate(ticker="BBRI", base_action="WATCH"),),
            as_of_date=date(2026, 7, 1),
        )
    )

    for cell in result.rows[0].cells:
        assert cell.capped_reason is None


def test_only_entry_authority_reason_survives_mixed_constraints():
    # Mixed reasons: only the entry-authority one becomes the capped_reason.
    entry_reason = "Setup smart_money_confirmed has no standalone entry authority"
    workflows = _all_workflows(
        response=_response(
            action="WATCH",
            match="MATCH",
            entry_authority=False,
            constraint_reasons=(
                "RISK_ON ENTER requires score >= 70",
                "Regime TRANSITIONING — ENTER capped to WATCH",
                entry_reason,
            ),
        )
    )
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    result = uc.execute(
        DailySetupLensImpactRequest(
            candidates=(DailySetupLensImpactCandidate(ticker="INDF", base_action="WATCH"),),
            as_of_date=date(2026, 7, 1),
        )
    )

    assert result.rows[0].cells[0].capped_reason == entry_reason


def test_one_setup_data_unavailable_produces_warning_cell_others_populate():
    setups = list(AVAILABLE_SWING_SETUPS)
    workflows = {
        setups[0]: FakeWorkflow(response=_response(action="WATCH")),
        setups[1]: FakeWorkflow(exc=PlanSwingDataUnavailable("BBRI")),
        setups[2]: FakeWorkflow(response=_response(action="ENTER")),
        setups[3]: FakeWorkflow(response=_response(action="AVOID")),
    }
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    result = uc.execute(
        DailySetupLensImpactRequest(
            candidates=(DailySetupLensImpactCandidate(ticker="BBRI", base_action="WATCH"),),
            as_of_date=date(2026, 7, 1),
        )
    )

    by_setup = {c.setup_name: c for c in result.rows[0].cells}
    failed = by_setup[setups[1]]
    assert failed.warning == "No local candle data for BBRI"
    assert failed.action is None
    assert failed.signal_score is None
    assert failed.setup_match == "NO_MATCH"
    # Other cells still populate normally.
    assert by_setup[setups[0]].action == "WATCH"
    assert by_setup[setups[2]].action == "ENTER"
    assert by_setup[setups[0]].warning is None


@pytest.mark.parametrize("exception_type", [RuntimeError, TypeError, ValueError])
def test_unexpected_setup_failure_propagates_same_exception(exception_type):
    failure = exception_type("unexpected setup failure")
    workflows = _all_workflows(response=_response())
    workflows[AVAILABLE_SWING_SETUPS[0]] = FakeWorkflow(exc=failure)
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    with pytest.raises(exception_type) as caught:
        uc.execute(
            DailySetupLensImpactRequest(
                candidates=(DailySetupLensImpactCandidate(ticker="BBRI", base_action="WATCH"),),
                as_of_date=date(2026, 7, 1),
            )
        )

    assert caught.value is failure


def test_mismatched_setup_workflow_keys_raises_value_error():
    workflows = _all_workflows(response=_response())
    workflows.pop(AVAILABLE_SWING_SETUPS[0])  # drop one key
    with pytest.raises(ValueError):
        DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    extra = _all_workflows(response=_response())
    extra["not-a-real-setup"] = FakeWorkflow(response=_response())
    with pytest.raises(ValueError):
        DailySetupLensImpactUseCase(setup_workflows=extra, request_defaults=DEFAULTS)


def test_requests_are_read_only_no_fetch_dependency():
    workflows = _all_workflows(response=_response())
    uc = DailySetupLensImpactUseCase(setup_workflows=workflows, request_defaults=DEFAULTS)

    uc.execute(
        DailySetupLensImpactRequest(
            candidates=(DailySetupLensImpactCandidate(ticker="BBRI", base_action="WATCH"),),
            as_of_date=date(2026, 7, 1),
        )
    )

    for wf in workflows.values():
        assert wf.received_requests, "workflow must have been invoked"
        for req in wf.received_requests:
            assert req.auto_refresh is False
            assert req.force_refresh is False
            assert req.strategy_name is None
            assert req.include_sentiment is False
            assert not hasattr(req, "with_market_context")
