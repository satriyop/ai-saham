"""ADR-067 §4 guards: readiness inputs, and no code identifiers in operator copy.

Two defects are pinned shut here.

**The side door.** ADR-067 §1 retired ``setup_quality`` from scoring, but
readiness was a second route from ``SetupEvidence`` to Action: the evaluator
took setup evidence, and ``DecisionPolicyService`` caps ``max_decision`` from
the readiness status. Retiring a group from scoring while leaving it able to
veto an action would be production authority through a side door. The guards
below assert the evaluator has no ``setup_evidence`` input at all — a
default-``None`` parameter would leave the door installed and merely unused.

**The leak.** The evaluator used to report ``missing_required_inputs =
("setup_evidence",)``, which the display rendered verbatim as ``setup readiness
UNAVAILABLE (missing: setup_evidence)``. That is a Python identifier printed at
an operator, and after this ADR it named a parameter that no longer exists. The
second half of this module is the ADR-067 §11 negative test: no operator-facing
readiness string may contain a code identifier, checked against a denylist
derived structurally from the value objects rather than hand-typed, so a newly
added field is covered without anyone remembering to add it.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from src.adapters.shared.decision_display import format_setup_readiness
from src.application.services.decision_policy import DecisionPolicyService
from src.application.services.setup_phase_readiness_evaluator import (
    SetupPhaseReadinessEvaluator,
)
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState
from src.domain.value_objects.setup_phase_readiness import (
    SetupPhaseReadiness,
    SetupReadinessStatus,
)
from src.domain.value_objects.signal_assessment import EntryQuality

_ROOT = Path(__file__).resolve().parents[3]
_EVALUATOR_PATH = _ROOT / "src" / "application" / "services" / "setup_phase_readiness_evaluator.py"

# Every module that turns a SetupPhaseReadiness into words a human reads.
_OPERATOR_SURFACES = (
    "src/adapters/shared/decision_display.py",
    "src/adapters/cli/screen_accum_single_display.py",
    "src/adapters/cli/inspect_signal_accum_commands.py",
    "src/adapters/tui/judge_desk_model.py",
    "src/adapters/tui/presenters/accum_engine_inspect_presenter.py",
)


def _phase(state: SetupPhaseState) -> SetupPhaseSnapshot:
    return SetupPhaseSnapshot(
        current_phase=state,
        previous_phase=None,
        phase_age_sessions=1,
        phase_detection_strength=0.9,
        phase_input_coverage=1.0,
        sequence_valid=True,
    )


def _every_reachable_readiness() -> list[SetupPhaseReadiness]:
    """Every SetupPhaseReadiness the evaluator can actually produce."""
    evaluator = SetupPhaseReadinessEvaluator()
    results = [
        evaluator.evaluate(setup_family="foreign-bounce", setup_phase=None),
    ]
    results.extend(
        evaluator.evaluate(setup_family="foreign-bounce", setup_phase=_phase(state))
        for state in SetupPhaseState
    )
    reachable = [r for r in results if r is not None]
    assert reachable, "the sweep would be vacuous with nothing to check"
    return reachable


# ── the side door ────────────────────────────────────────────────────────────


def test_evaluator_does_not_accept_setup_evidence() -> None:
    """Deleted, not defaulted: no parameter, no route, nothing to pass."""
    parameters = inspect.signature(SetupPhaseReadinessEvaluator.evaluate).parameters
    assert "setup_evidence" not in parameters
    assert set(parameters) == {"self", "setup_family", "setup_phase"}


def test_evaluator_module_references_no_setup_evidence_symbol() -> None:
    """AST, not grep: the docstring may explain the retirement; code may not
    reintroduce it under any name."""
    tree = ast.parse(_EVALUATOR_PATH.read_text(encoding="utf-8"))
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.alias):
            used.update(part for part in node.name.split(".") if part)
        elif isinstance(node, ast.arg):
            used.add(node.arg)
        elif isinstance(node, ast.ImportFrom) and node.module:
            used.update(part for part in node.module.split(".") if part)
    assert "setup_evidence" not in used
    assert "SetupEvidence" not in used


def test_no_production_call_site_passes_setup_evidence_to_the_evaluator() -> None:
    """The evaluator is constructed and called in exactly one production place,
    and that call names only the two surviving inputs."""
    call_sites: list[tuple[str, set[str]]] = []
    for path in sorted((_ROOT / "src").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "SetupPhaseReadinessEvaluator" not in source:
            continue
        if path == _EVALUATOR_PATH:
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "evaluate"):
                continue
            keywords = {kw.arg for kw in node.keywords if kw.arg}
            call_sites.append((str(path.relative_to(_ROOT)), keywords))

    assert call_sites, "expected at least one production call site to inspect"
    for module, keywords in call_sites:
        assert "setup_evidence" not in keywords, module
        assert keywords == {"setup_family", "setup_phase"}, module


def test_setup_evidence_value_object_survives_for_the_diagnostic_lens() -> None:
    """ADR-067 §14: retiring the readiness route must not delete the VO that
    the ``--setup`` diagnostic lens is built from."""
    fields = {f.name for f in dataclasses.fields(SetupEvidence)}
    assert {"setup_match", "match_strength", "failed_gates"} <= fields


# ── phase caps preserved bit-for-bit ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("phase_state", "expected_cap"),
    [
        (SetupPhaseState.DISTRIBUTION, EntryQuality.AVOID),
        (SetupPhaseState.FAILED, EntryQuality.AVOID),
        (SetupPhaseState.EXHAUSTION, EntryQuality.WATCH),
        (SetupPhaseState.ACCUMULATION, EntryQuality.WATCH),
        (SetupPhaseState.NONE, EntryQuality.WATCH),
    ],
)
def test_phase_caps_survive_the_readiness_rewiring(phase_state, expected_cap) -> None:
    """End to end through the real evaluator and the real policy — the caps
    ADR-067 §4 promises are unchanged, not just the statuses."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="foreign-bounce",
        setup_phase=_phase(phase_state),
    )
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        signal_authority_coverage=1.0,
        market_context=None,
        setup_family="foreign-bounce",
        setup_readiness=readiness,
    )
    assert result.entry_quality == expected_cap


def test_no_family_applies_no_readiness_cap() -> None:
    """Flow-only discovery — the 7,379-of-7,764 majority — is untouched."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(setup_family=None, setup_phase=None)
    assert readiness is None
    result = DecisionPolicyService().resolve(
        entry_quality=EntryQuality.ENTER,
        score=90,
        signal_authority_coverage=1.0,
        market_context=None,
        setup_family=None,
        setup_readiness=readiness,
    )
    assert result.entry_quality == EntryQuality.ENTER


# ── the leak: no code identifiers in operator copy ───────────────────────────


def _code_identifier_denylist() -> frozenset[str]:
    """Internal Python names that must never reach an operator.

    Derived from the value objects rather than typed by hand, so a field added
    to ``SetupEvidence`` or ``SetupPhaseReadiness`` is covered automatically.
    Restricted to multi-part snake_case names: single common words like
    ``trend`` or ``rsi`` are ordinary English and prose is allowed to use them.
    """
    names = {f.name for f in dataclasses.fields(SetupEvidence)}
    names |= {f.name for f in dataclasses.fields(SetupPhaseReadiness)}
    names |= set(inspect.signature(SetupPhaseReadinessEvaluator.evaluate).parameters)
    names.add("setup_evidence")  # the retired parameter itself
    names.add("setup_quality")  # the group ADR-067 §1 retired
    denylist = frozenset(name for name in names if "_" in name)
    assert "setup_evidence" in denylist and "entry_authority" in denylist
    return denylist


def test_evaluator_emits_no_code_identifier_in_any_reachable_output() -> None:
    """The reason strings themselves — before any adapter touches them."""
    denylist = _code_identifier_denylist()
    for readiness in _every_reachable_readiness():
        emitted = (
            *readiness.missing_required_inputs,
            *readiness.failed_requirements,
            readiness.setup_family,
        )
        for text in emitted:
            leaked = sorted(name for name in denylist if name in text)
            assert not leaked, f"{readiness.status.value} emits {leaked} in {text!r}"


def test_rendered_readiness_copy_contains_no_code_identifier() -> None:
    """The ADR-067 §11 negative test, at the surface the operator actually reads.

    Deleting the old ``missing: setup_evidence`` assertion would prove nothing;
    this renders every readiness the evaluator can produce, in every style, and
    fails on any internal identifier in the result.
    """
    denylist = _code_identifier_denylist()
    rendered: list[str] = []
    for readiness in _every_reachable_readiness():
        for style in ("full", "why"):
            rendered.append(format_setup_readiness(readiness, style=style))
            rendered.append(
                format_setup_readiness(readiness, setup_family="foreign-bounce", style=style)
            )
    rendered.append(format_setup_readiness(None, style="full"))
    rendered.append(format_setup_readiness(None, setup_family="foreign-bounce", style="full"))

    assert any(text for text in rendered), "nothing was rendered — the guard would be vacuous"
    for text in rendered:
        leaked = sorted(name for name in denylist if name in text)
        assert not leaked, f"operator copy leaks {leaked}: {text!r}"


def test_no_operator_surface_hardcodes_a_retired_identifier_in_its_copy() -> None:
    """Belt and braces on the rendering side: the displays may *match* against
    an identifier when reading upstream constraint text, but must never build
    one into a string they hand back."""
    denylist = _code_identifier_denylist()
    offenders: list[str] = []
    for relative in _OPERATOR_SURFACES:
        path = _ROOT / relative
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            for inner in ast.walk(node.value):
                if not (isinstance(inner, ast.Constant) and isinstance(inner.value, str)):
                    continue
                offenders.extend(
                    f"{relative}:{inner.lineno}:{name}" for name in denylist if name in inner.value
                )
    assert offenders == [], f"code identifiers built into returned operator copy: {offenders}"


def test_unavailable_still_renders_a_reason_rather_than_degrading_to_a_bare_status() -> None:
    """Preserves the intent of the display test this ADR replaced: removing the
    identifier must not cost the operator the explanation."""
    readiness = SetupPhaseReadinessEvaluator().evaluate(
        setup_family="pullback",
        setup_phase=_phase(SetupPhaseState.ACCUMULATION),
    )
    assert readiness.status == SetupReadinessStatus.UNAVAILABLE
    text = format_setup_readiness(readiness, style="full")
    assert text == "setup readiness UNAVAILABLE [pullback] (setup match not evaluated)"
