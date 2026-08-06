"""ADR-067 retirement guards: one production evidence group, no blend.

These are the negative tests named in the ADR-067 task's Testing Expectations —
the ones that prove the defect cannot come back rather than that today's
arithmetic is right. Two things are guarded:

1. No scoring-path module may reference ``setup_quality`` again, in any form
   other than the resolver's fail-closed rejection message.
2. No typed config object may carry a ``setup_quality`` attribute anywhere in
   ``src/``, which is what a silent reintroduction would look like.

The Alpha/Trigger projection keeps a *diagnostic* slot of the same name, with
its own ``group_weights`` and ``route_fractions``. That is a different
namespace, it is addressed by dict key rather than by attribute, and ADR-067
deliberately does not retire it — so the guards below are written to
distinguish the two rather than to ban the string globally.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.application.services.signal_evidence_group_scorer import SignalEvidenceGroupScorer

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"

# The canonical evidence-group scoring path: everything that computes, resolves,
# conditions, or declares the production evidence basis.
_SCORING_PATH_MODULES = (
    "src/application/services/signal_evidence_group_scorer.py",
    "src/application/services/signal_legacy_regime_conditioning.py",
    "src/application/services/accumulation_policy_snapshot_payloads.py",
    "src/application/services/engine_bootstrap/signal_scoring_config_resolver.py",
    "src/application/use_case/assess_signal_evidence_use_case.py",
)


def _string_constants_outside_raises(tree: ast.AST) -> list[ast.Constant]:
    """Every string-literal node that is not part of a fail-closed rejection.

    A rejection is either the ``raise`` itself or the ``if`` that guards one and
    does nothing else, so ``if "setup_quality" in evidence_groups: raise ...``
    is exempt in both halves while any other mention is reported.
    """
    raised: set[int] = set()
    for node in ast.walk(tree):
        is_rejection = isinstance(node, ast.Raise) or (
            isinstance(node, ast.If)
            and not node.orelse
            and all(isinstance(stmt, ast.Raise) for stmt in node.body)
        )
        if is_rejection:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    raised.add(id(inner))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in raised
    ]


@pytest.mark.parametrize("module", _SCORING_PATH_MODULES)
def test_no_scoring_path_module_references_the_retired_group(module: str) -> None:
    """ADR-067: the retired group must not survive anywhere that scores.

    A docstring or comment mentioning the retirement is fine — those are not
    string constants in expression position and carry no behaviour. What is
    banned is a live reference: a dict key read, a default, or a declared
    component name. The resolver's rejection message is exempt because its
    whole purpose is to name the retired key while refusing it.
    """
    path = _ROOT / module
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstring_nodes = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    offenders = [
        node.value
        for node in _string_constants_outside_raises(tree)
        if "setup_quality" in node.value and id(node) not in docstring_nodes
    ]
    assert offenders == [], (
        f"{module} still references the retired setup_quality evidence group "
        f"outside a rejection message: {offenders}"
    )


def test_no_typed_config_attribute_named_setup_quality_survives() -> None:
    """A reintroduced group would show up as attribute access, not a dict key.

    The Alpha/Trigger diagnostic slot is addressed as
    ``group_weights["setup_quality"]``, so it is unaffected by this guard —
    which is exactly the distinction ADR-067 draws between the retired
    production evidence group and the surviving diagnostic projection.
    """
    offenders: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "setup_quality":
                offenders.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert offenders == [], (
        "setup_quality is readable as a typed config attribute again; ADR-067 "
        f"retired the evidence group with no compatibility path: {offenders}"
    )


@pytest.mark.parametrize("flow_score", [0.0, 20.0, 55.5, 100.0])
def test_renormalize_returns_the_flow_score_unweighted(flow_score: float) -> None:
    """The signal score IS the flow group score — no weight, no denominator.

    ``renormalize`` no longer takes a config at all, which is the structural
    proof that nothing is being weighed: there is no weight in scope to apply.
    """
    assert SignalEvidenceGroupScorer.renormalize(flow_score, True) == flow_score


def test_renormalize_uses_the_neutral_prior_when_no_group_is_present() -> None:
    """Absent evidence is never neutral-*filled* into a group average.

    With no group present there is no evidence at all, and the score is the
    explicit 50.0 prior — unchanged from the two-group form.
    """
    assert SignalEvidenceGroupScorer.renormalize(90.0, False) == 50.0
