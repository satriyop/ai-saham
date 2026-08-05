"""ADR-067 §3: `plan swing` carries the screen verdict; it never judges.

These tests replace the previous canonical-evidence-construction suite for
this module. Plan no longer assembles a `CanonicalSignalEvidenceInput` and no
longer re-scores through `SignalEngine.evaluate_swing_trade_setup()`, so the
properties worth locking in are:

1. Screen's TradeSetup is inherited verbatim — with *no* flag combination that
   can override it (this is the ADR-067 behaviour change).
2. Plan composes a structure-only TradeSetup only when screen never judged the
   ticker.
3. The composer cannot regain the retired mechanism: a source-level guard
   fails if any plan-swing application module names
   `CanonicalSignalEvidenceInput`, its group inputs, `canonical_evidence`, or
   `evaluate_swing_trade_setup` (ADR-067 §11 negative test).
"""

from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.dto import plan_swing as plan_swing_dto
from src.application.dto.assess_signal import AssessSignalResponse
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.plan_swing_decision_composer import (
    PlanSwingDecisionComposer,
)
from src.application.services.plan_swing_workflow_state import (
    PlanSwingWorkflowState,
)
from src.application.services.swing_judgment_authority import SCREEN_JUDGMENT_WARNING
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.signal_assessment import (
    SWING_TRADE_SETUP_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup

TICKER = "BBCA"
SNAP = date(2026, 7, 17)


def _request(**overrides):
    params = dict(
        ticker=TICKER,
        today=SNAP,
        strategy_name=None,
        setup_name=None,
        window=200,
        flow_window=20,
        capital=None,
        risk_pct=1.0,
        entry_price=None,
        atr_mult=2.0,
        rr=2.0,
        include_sentiment=False,
        include_flow_detail=False,
        include_signal_detail=False,
        include_risk_detail=False,
        include_market_detail=False,
        sentiment_verbose=False,
        auto_refresh=False,
        force_refresh=False,
        with_market_context=False,
        regime_universe="lq45",
        benchmark="COMPOSITE",
        db_path=Path("/tmp/does-not-exist.db"),
        with_technical_gate=False,
    )
    params.update(overrides)
    return plan_swing_dto.PlanSwingWorkflowRequest(**params)


def _effective_session() -> EffectiveMarketSession:
    decision_at = datetime(SNAP.year, SNAP.month, SNAP.day, 20, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=SNAP,
        analysis_as_of=SNAP,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _signal_response(score: int = 72) -> AssessSignalResponse:
    assessment = SignalAssessment(
        identity=SWING_TRADE_SETUP_IDENTITY,
        ticker=TICKER,
        score=score,
        strength=SignalStrength.MODERATE,
        entry_quality=EntryQuality.ENTER,
        breakdown=(("setup", 60.0), ("flow", 40.0)),
        rationale=("test rationale",),
        snapshot_date=SNAP,
        signal_authority_coverage=None,
    )
    return AssessSignalResponse(ticker=TICKER, assessment=assessment)


def _trade_setup(action: SetupAction, score: int, rationale: str) -> TradeSetup:
    return TradeSetup(
        ticker=TICKER,
        snapshot_date=SNAP,
        action=action,
        signal_score=score,
        signal_score_raw=score,
        signal_strength=SignalStrength.MODERATE,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale=rationale,
    )


class _EngineThatMustNotJudge:
    """Any scoring entry point on this engine is a contract violation for the
    plan surface (ADR-067 §3)."""

    def foreign_flow_quality_from_accum_score(self, score):
        return None

    def bandar_max_range(self, num_optional):
        return 6

    def evaluate_swing_trade_setup(self, *args, **kwargs):
        raise AssertionError("plan must not re-score: ADR-067 §3")

    def evaluate_accumulation_discovery(self, *args, **kwargs):
        raise AssertionError("plan must not re-score: ADR-067 §3")


class _RiskComposerThatMustNotRecompose:
    def __init__(self, plan_setup: TradeSetup | None) -> None:
        self._plan_setup = plan_setup

    def compose_trade_setup(self, **kwargs):
        return self._plan_setup, []

    def compose_market_context_preview(self, **kwargs):
        return None, None, None, []

    def recompose_after_signal_rescore(self, **kwargs):
        raise AssertionError("plan must not recompose after a re-score: ADR-067 §3")


def _state_with_screen_verdict(screen_setup: TradeSetup | None) -> PlanSwingWorkflowState:
    from src.application.dto.signal_evidence_execution_context import (
        SignalEvidenceExecutionContext,
    )

    candidate = SimpleNamespace(
        trade_setup=screen_setup,
        signal_assessment=_signal_response(50),
        bandar_detector=None,
        seasonal_edge=None,
        analyst_consensus=None,
        forward_estimates=None,
        current_price=None,
        accum_score=0.0,
        insider_net_buy_ratio=None,
    )
    state = PlanSwingWorkflowState()
    state.accumulation_evaluation = SimpleNamespace(candidate=candidate)
    state.signal_evidence_execution_context = SignalEvidenceExecutionContext(
        effective_session=_effective_session(),
        source_availability_use_case=None,
    )
    state.signal_assessment = candidate.signal_assessment
    state.signal_assessment_availability = plan_swing_dto.SignalAssessmentAvailability(
        status=plan_swing_dto.SignalAssessmentStatus.AVAILABLE
    )
    state.risk_response = SimpleNamespace()
    return state


# --- 1/2: screen verdict is inherited, under every flag combination ----------


@pytest.mark.parametrize(
    ("with_market_context", "with_technical_gate"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_compose_trade_setup_inherits_screen_action_under_every_flag_combination(
    with_market_context: bool,
    with_technical_gate: bool,
) -> None:
    """ADR-067 §3 behaviour change: the re-judge flags no longer buy an Action.

    Before ADR-067, `with_market_context`/`with_technical_gate` unlocked a
    plan-side Action recompute that replaced screen's verdict. They must now
    change nothing about which TradeSetup the plan verdict shows.
    """
    screen_setup = _trade_setup(SetupAction.WATCH, 55, "screen")
    plan_setup = _trade_setup(SetupAction.ENTER, 90, "plan")

    state = _state_with_screen_verdict(screen_setup)
    composer = PlanSwingDecisionComposer(
        risk_trade_setup_composer=_RiskComposerThatMustNotRecompose(plan_setup),
        signal_engine=_EngineThatMustNotJudge(),
    )

    result = composer.compose_trade_setup_and_preview(
        _request(
            with_market_context=with_market_context,
            with_technical_gate=with_technical_gate,
        ),
        state,
    )

    assert result.trade_setup is screen_setup
    assert result.verdict.trade_setup is screen_setup
    assert result.trade_setup.action == SetupAction.WATCH
    assert SCREEN_JUDGMENT_WARNING in result.warnings


def test_compose_trade_setup_uses_plan_structure_when_screen_never_judged() -> None:
    """A ticker screen never judged has no verdict to inherit — plan's
    structure-only TradeSetup stands (ADR-054 S3 rule 2)."""
    plan_setup = _trade_setup(SetupAction.AVOID, 20, "plan")

    state = _state_with_screen_verdict(None)
    composer = PlanSwingDecisionComposer(
        risk_trade_setup_composer=_RiskComposerThatMustNotRecompose(plan_setup),
        signal_engine=_EngineThatMustNotJudge(),
    )

    result = composer.compose_trade_setup_and_preview(_request(), state)

    assert result.trade_setup is plan_setup
    assert result.verdict.trade_setup is plan_setup
    assert SCREEN_JUDGMENT_WARNING not in result.warnings


# --- 3: the post-evidence step carries forward and nothing else -------------


@pytest.mark.parametrize(
    ("with_market_context", "with_technical_gate"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_carry_forward_freezes_screen_action_and_never_rescores(
    with_market_context: bool,
    with_technical_gate: bool,
) -> None:
    screen_setup = _trade_setup(SetupAction.WATCH, 60, "screen")
    plan_temp = _trade_setup(SetupAction.ENTER, 99, "plan-temp")

    state = _state_with_screen_verdict(screen_setup)
    composer = PlanSwingDecisionComposer(
        risk_trade_setup_composer=_RiskComposerThatMustNotRecompose(plan_temp),
        signal_engine=_EngineThatMustNotJudge(),
    )
    # Whatever the earlier structure pass left behind is irrelevant to Action.
    state.trade_setup = plan_temp
    state.verdict = plan_swing_dto.SwingVerdict(
        trade_setup=plan_temp,
        signal_assessment=state.signal_assessment,
        risk_response=None,
        market_regime=None,
        signal_assessment_availability=state.signal_assessment_availability,
    )

    # Flags are inert here by construction; parametrised to prove it.
    _ = (with_market_context, with_technical_gate)
    result = composer.carry_forward_screen_verdict(state)

    assert result.trade_setup is screen_setup
    assert result.trade_setup.action == SetupAction.WATCH
    assert result.verdict.trade_setup is screen_setup
    assert SCREEN_JUDGMENT_WARNING in result.warnings
    # Signal assessment is screen's, untouched — no enriched re-score exists.
    assert result.signal_assessment.assessment.score == 50


def test_carry_forward_leaves_plan_structure_intact_without_screen_verdict() -> None:
    plan_temp = _trade_setup(SetupAction.AVOID, 20, "plan-temp")

    state = _state_with_screen_verdict(None)
    composer = PlanSwingDecisionComposer(
        risk_trade_setup_composer=_RiskComposerThatMustNotRecompose(plan_temp),
        signal_engine=_EngineThatMustNotJudge(),
    )
    state.trade_setup = plan_temp
    state.verdict = plan_swing_dto.SwingVerdict(
        trade_setup=plan_temp,
        signal_assessment=state.signal_assessment,
        risk_response=None,
        market_regime=None,
        signal_assessment_availability=state.signal_assessment_availability,
    )

    result = composer.carry_forward_screen_verdict(state)

    assert result.trade_setup is plan_temp
    assert result.verdict.trade_setup is plan_temp
    assert result.warnings == []


def test_carry_forward_appends_the_screen_judgment_note_only_once() -> None:
    screen_setup = _trade_setup(SetupAction.WATCH, 60, "screen")
    state = _state_with_screen_verdict(screen_setup)
    composer = PlanSwingDecisionComposer(
        risk_trade_setup_composer=_RiskComposerThatMustNotRecompose(None),
        signal_engine=_EngineThatMustNotJudge(),
    )
    state.warnings.append(SCREEN_JUDGMENT_WARNING)

    result = composer.carry_forward_screen_verdict(state)

    assert result.warnings.count(SCREEN_JUDGMENT_WARNING) == 1


# --- 4: source-level guard (ADR-067 §11 negative test) ----------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICES_DIR = _REPO_ROOT / "src" / "application" / "services"

_PLAN_SWING_APPLICATION_MODULES = (
    *sorted(_SERVICES_DIR.glob("plan_swing_*.py")),
    _SERVICES_DIR / "swing_judgment_authority.py",
    _SERVICES_DIR / "swing_trade_plan_builder.py",
    _REPO_ROOT / "src" / "application" / "use_case" / "plan_swing_workflow_use_case.py",
)

# Identifiers whose presence anywhere on the plan surface would mean plan had
# regained a route to producing its own Action.
_FORBIDDEN_IDENTIFIERS = frozenset(
    {
        "CanonicalSignalEvidenceInput",
        "SetupEvidenceGroupInput",
        "FlowEvidenceGroupInput",
        "canonical_evidence",
        "evaluate_swing_trade_setup",
        "evaluate_accumulation_discovery",
        "allow_action_recompute",
        "allow_recompute",
    }
)


def _referenced_identifiers(module_path: Path) -> set[str]:
    """Every name the module actually references in code.

    Docstrings and comments are deliberately excluded — this must fail on a
    real re-introduction, not on prose describing the retirement.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            names.add(node.arg)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.name.rsplit(".", 1)[-1])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def test_plan_swing_modules_are_discovered_by_the_source_guard() -> None:
    # A guard that silently globs nothing would pass forever.
    paths = {p.name for p in _PLAN_SWING_APPLICATION_MODULES}
    assert "plan_swing_decision_composer.py" in paths
    assert "plan_swing_risk_trade_setup.py" in paths
    assert len(_PLAN_SWING_APPLICATION_MODULES) >= 8
    for path in _PLAN_SWING_APPLICATION_MODULES:
        assert path.is_file(), path


@pytest.mark.parametrize("module_path", _PLAN_SWING_APPLICATION_MODULES, ids=lambda p: p.name)
def test_plan_surface_never_constructs_canonical_signal_evidence(module_path: Path) -> None:
    """ADR-067 §11: fail if `plan swing` regains a scoring/judgment route."""
    offenders = sorted(_referenced_identifiers(module_path) & _FORBIDDEN_IDENTIFIERS)
    assert offenders == [], (
        f"{module_path} references retired plan-judgment identifiers {offenders}. "
        "ADR-067 §3: plan carries the screen verdict and must neither assemble "
        "canonical evidence nor invoke a SignalEngine scoring entry point."
    )


def test_source_guard_detects_a_reintroduction(tmp_path: Path) -> None:
    """Sensitivity counterexample — proves the guard above can actually fail."""
    offending = tmp_path / "plan_swing_regression.py"
    offending.write_text(
        "def judge(engine, ctx, evidence):\n"
        "    return engine.evaluate_swing_trade_setup(ctx, canonical_evidence=evidence)\n",
        encoding="utf-8",
    )
    assert _referenced_identifiers(offending) & _FORBIDDEN_IDENTIFIERS == {
        "canonical_evidence",
        "evaluate_swing_trade_setup",
    }
