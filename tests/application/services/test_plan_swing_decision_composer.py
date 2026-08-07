"""RC-04 plan composer carries one screen reference and cannot judge."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.dto import plan_swing as plan_swing_dto
from src.application.services.plan_swing_decision_composer import PlanSwingDecisionComposer
from src.application.services.plan_swing_workflow_state import PlanSwingWorkflowState
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup

SNAP = date(2026, 8, 7)


def _request() -> plan_swing_dto.PlanSwingWorkflowRequest:
    return plan_swing_dto.PlanSwingWorkflowRequest(
        ticker="BBCA",
        today=SNAP,
        strategy_name=None,
        setup_name=None,
        window=7,
        flow_window=20,
        capital=None,
        risk_pct=1.0,
        entry_price=None,
        atr_mult=1.5,
        rr=2.0,
        include_sentiment=False,
        include_flow_detail=False,
        include_signal_detail=False,
        sentiment_verbose=False,
        auto_refresh=False,
        force_refresh=False,
        db_path=Path("/tmp/does-not-exist.db"),
    )


def _setup() -> TradeSetup:
    return TradeSetup(
        ticker="BBCA",
        snapshot_date=SNAP,
        action=SetupAction.WATCH,
        signal_score=70,
        signal_score_raw=70,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="screen",
    )


def test_composer_preserves_one_exact_reference_and_screen_components() -> None:
    setup = _setup()
    signal = object()
    risk = object()
    candidate = SimpleNamespace(
        ticker="BBCA",
        trade_setup=setup,
        signal_assessment=signal,
        risk_assessment=risk,
    )
    state = PlanSwingWorkflowState(
        accumulation_evaluation=SimpleNamespace(candidate=candidate, analysis_date=SNAP)
    )

    result = PlanSwingDecisionComposer().resolve_screen_judgment(_request(), state)

    assert result.judgment_ref is result.verdict.judgment_ref
    assert result.judgment_ref.trade_setup is setup
    assert result.verdict.signal_assessment is signal
    assert result.verdict.risk_assessment is risk


def test_composer_missing_setup_never_creates_action() -> None:
    candidate = SimpleNamespace(
        ticker="BBCA",
        trade_setup=None,
        signal_assessment=object(),
        risk_assessment=object(),
    )
    state = PlanSwingWorkflowState(
        accumulation_evaluation=SimpleNamespace(candidate=candidate, analysis_date=SNAP)
    )

    result = PlanSwingDecisionComposer().resolve_screen_judgment(_request(), state)

    assert result.judgment_ref.trade_setup is None
    assert result.verdict.trade_setup is None


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICES_DIR = _REPO_ROOT / "src" / "application" / "services"
_PLAN_SWING_APPLICATION_MODULES = (
    *sorted(_SERVICES_DIR.glob("plan_swing_*.py")),
    _SERVICES_DIR / "swing_judgment_authority.py",
    _SERVICES_DIR / "swing_trade_plan_builder.py",
    _REPO_ROOT / "src" / "application" / "use_case" / "plan_swing_workflow_use_case.py",
)
_FORBIDDEN_IDENTIFIERS = frozenset(
    {
        "AssessTradeSetupUseCase",
        "AssessTradeSetupRequest",
        "plan_recomputed",
        "market_context_trade_setup_preview",
        "evaluate_swing_trade_setup",
        "evaluate_accumulation_discovery",
    }
)


def _referenced_identifiers(module_path: Path) -> set[str]:
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


def test_plan_swing_modules_are_discovered_by_source_guard() -> None:
    paths = {path.name for path in _PLAN_SWING_APPLICATION_MODULES}
    assert "plan_swing_decision_composer.py" in paths
    assert "plan_swing_risk_trade_setup.py" not in paths
    assert len(_PLAN_SWING_APPLICATION_MODULES) >= 8
    assert all(path.is_file() for path in _PLAN_SWING_APPLICATION_MODULES)


@pytest.mark.parametrize("module_path", _PLAN_SWING_APPLICATION_MODULES, ids=lambda p: p.name)
def test_plan_surface_has_no_action_producer_identifier(module_path: Path) -> None:
    offenders = sorted(_referenced_identifiers(module_path) & _FORBIDDEN_IDENTIFIERS)
    assert offenders == [], f"{module_path} retains plan Action identifiers: {offenders}"


def test_source_guard_detects_reintroduction(tmp_path: Path) -> None:
    offending = tmp_path / "plan_swing_regression.py"
    offending.write_text(
        "def judge(use_case, request):\n"
        "    return use_case.execute(AssessTradeSetupRequest(**request))\n",
        encoding="utf-8",
    )
    assert _referenced_identifiers(offending) & _FORBIDDEN_IDENTIFIERS == {
        "AssessTradeSetupRequest"
    }
