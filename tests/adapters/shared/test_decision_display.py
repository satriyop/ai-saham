"""Shared decision_display formatters — honesty and single-path contracts."""

from __future__ import annotations

from types import SimpleNamespace

from src.adapters.shared.decision_display import (
    format_accum_breakdown,
    format_action_why,
    format_decision_stack,
    format_market_context_lines,
    format_setup_readiness,
    format_unknown_gates,
    unevaluable_gates,
)


def _readiness(
    *,
    status: str = "UNAVAILABLE",
    family: str = "pullback",
    missing: tuple[str, ...] = ("setup match not evaluated",),
    failed: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        status=SimpleNamespace(value=status),
        setup_family=family,
        missing_required_inputs=missing,
        failed_requirements=failed,
        current_phase=None,
    )


def _candidate(
    *,
    coverage: float = 0.0,
    readiness: object | None = "unavailable",
    gate_triggered=None,
    setup_family: str | None = None,
) -> SimpleNamespace:
    if readiness == "unavailable":
        setup_readiness = _readiness()
        constraint_reasons = (
            "RISK_ON ENTER requires signal_authority_coverage >= 70%",
            "Setup readiness UNAVAILABLE caps ENTER to WATCH",
        )
    elif readiness == "none":
        setup_readiness = None
        # Flow-only discovery: no setup readiness constraint from DecisionPolicy
        constraint_reasons = ("RISK_ON ENTER requires signal_authority_coverage >= 70%",)
    else:
        setup_readiness = readiness
        constraint_reasons = ("RISK_ON ENTER requires signal_authority_coverage >= 70%",)

    assessment = SimpleNamespace(
        score=79,
        strength=SimpleNamespace(value="STRONG"),
        signal_authority_coverage=coverage,
        decision_constraints=SimpleNamespace(
            constraint_reasons=constraint_reasons,
            max_decision="WATCH",
            regime=None,
        ),
        setup_readiness=setup_readiness,
    )
    components = (
        SimpleNamespace(key="cons", score_points=28.5, status=SimpleNamespace(value="AVAILABLE")),
        SimpleNamespace(key="bb", score_points=None, status=SimpleNamespace(value="DISABLED")),
    )
    return SimpleNamespace(
        ticker="PGEO",
        accum_score=62.2,
        setup_family=setup_family,
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            rationale="Signal 79/100 | gate: open",
            signal_strength=SimpleNamespace(value="STRONG"),
        ),
        signal_assessment=SimpleNamespace(
            assessment=assessment,
            setup_readiness=setup_readiness,
            signal_authority_coverage=coverage,
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=gate_triggered,
            risk_level_name="OPEN" if gate_triggered is None else "BLOCKED",
        ),
        accum_score_breakdown=SimpleNamespace(components=components, accum_score=62.2),
    )


def test_readiness_none_no_family_is_flow_only_full():
    text = format_setup_readiness(None, setup_family=None, style="full")
    assert "flow-only" in text
    assert "READY" not in text


def test_readiness_none_no_family_silent_in_why_style():
    assert format_setup_readiness(None, setup_family=None, style="why") == ""


def test_readiness_none_with_family_is_defect():
    text = format_setup_readiness(None, setup_family="pullback", style="full")
    assert "defect" in text
    assert "pullback" in text
    assert "READY" not in text


def test_readiness_unavailable_shows_its_reason():
    text = format_setup_readiness(_readiness(), style="full")
    assert "UNAVAILABLE" in text
    assert "(setup match not evaluated)" in text
    assert "pullback" in text


def test_readiness_never_prints_code_identifiers():
    from types import SimpleNamespace

    readiness = SimpleNamespace(
        status=SimpleNamespace(value="UNAVAILABLE"),
        setup_family="pullback",
        missing_required_inputs=("setup_evidence", "flow_ev"),
        failed_requirements=("setup_match",),
        current_phase=None,
    )
    text = format_setup_readiness(readiness, setup_family="pullback", style="full")
    assert "setup_evidence" not in text
    assert "flow_ev" not in text
    assert "setup match inputs" in text
    assert "flow evidence" in text
    incomplete = format_setup_readiness(
        SimpleNamespace(
            status=SimpleNamespace(value="INCOMPLETE"),
            setup_family="pullback",
            missing_required_inputs=(),
            failed_requirements=("setup_match",),
            current_phase=None,
        ),
        style="full",
    )
    assert "setup_match" not in incomplete
    assert "setup match" in incomplete


def test_never_invent_ready_when_none():
    for style in ("full", "why"):
        phrase = format_setup_readiness(None, style=style)  # type: ignore[arg-type]
        assert "READY" not in phrase


def test_format_accum_breakdown():
    c = _candidate()
    text = format_accum_breakdown(c, accum_display="62.2")
    assert text.startswith("62.2 = ")
    assert "cons 28.5" in text
    assert "bb off" in text


def test_format_action_why_includes_authority_readiness_gate():
    c = _candidate(coverage=0.0)
    why = format_action_why(c, gate="OPEN")
    assert "authority 0%" in why
    assert "setup readiness UNAVAILABLE" in why
    assert "(setup match not evaluated)" in why
    assert "gate open" in why
    assert "recipe" not in why.lower()


def test_format_action_why_flow_only_no_fake_readiness():
    c = _candidate(readiness="none", setup_family=None)
    why = format_action_why(c, gate="OPEN")
    assert "READY" not in why
    # Why style stays quiet on flow-only (not a defect)
    assert "setup readiness" not in why or "UNAVAILABLE" not in why
    assert "gate open" in why


def test_format_decision_stack_scannable():
    c = _candidate()
    lines = format_decision_stack(c, action="WATCH", gate="OPEN", signal="79")
    text = "\n".join(lines)
    assert "Decision" in text
    assert "Action WATCH · Gate OPEN" in text
    assert "← Signal 79" in text
    assert "coverage 0%" in text
    assert "← Risk OPEN" in text
    assert "← Why:" in text


def test_format_market_context_display_only():
    mc = SimpleNamespace(
        regime=SimpleNamespace(value="RISK_ON"),
        conviction=0.72,
        regime_confidence=0.55,
        regime_stability="STABLE",
        days_in_regime=4,
        staleness_warning=None,
        coverage_warning=None,
        transition_warning=None,
    )
    lines = format_market_context_lines(mc)
    text = "\n".join(lines)
    assert "regime RISK_ON" in text
    assert "conviction 0.72" in text
    assert "stability STABLE" in text


def test_format_market_context_absent_honest():
    text = "\n".join(format_market_context_lines(None, candidate=_candidate()))
    assert "not evaluated" in text or "not on this screen" in text
    assert "RISK_ON" not in text or "decision constraints" in text


# ── Unevaluable risk gates ──────────────────────────────────────────────────
# An open gate with unknowns is not an all-clear: those gates never checked
# anything. The operator must see "N gates unknown", not an implied all-clear.


def _candidate_with_unknown_gates(*names: str, gate_triggered=None):
    c = _candidate(gate_triggered=gate_triggered)
    c.risk_assessment = SimpleNamespace(
        gate_triggered=gate_triggered,
        risk_level_name="OPEN" if gate_triggered is None else "BLOCKED",
        unevaluable_gates=tuple(names),
    )
    return c


def test_no_unknown_gates_reads_as_a_plain_open_gate():
    c = _candidate_with_unknown_gates()
    assert unevaluable_gates(c) == ()
    assert format_unknown_gates(()) == ""
    why = format_action_why(c, gate="OPEN")
    assert "gate open" in why
    assert "unknown" not in why


def test_open_gate_with_unknowns_is_never_an_implied_all_clear():
    c = _candidate_with_unknown_gates("FundamentalGate", "BandarGate")
    why = format_action_why(c, gate="OPEN")
    assert "2 gates unknown" in why
    assert "FundamentalGate" in why
    assert "BandarGate" in why
    # The bare phrase must not stand alone.
    assert "gate open, 2 gates unknown" in why


def test_single_unknown_gate_is_singular():
    assert format_unknown_gates(("FundamentalGate",)) == "1 gate unknown (FundamentalGate)"


def test_decision_stack_risk_line_carries_the_unknown_count():
    c = _candidate_with_unknown_gates("FundamentalGate")
    text = "\n".join(format_decision_stack(c, action="WATCH", gate="OPEN", signal="79"))
    assert "← Risk OPEN · 1 gate unknown (FundamentalGate)" in text


def test_a_blocked_gate_still_reports_what_was_never_checked():
    c = _candidate_with_unknown_gates("FundamentalGate", gate_triggered="FreeFloatGate")
    text = "\n".join(format_decision_stack(c, action="AVOID", gate="BLOCKED", signal="40"))
    assert "BLOCKED" in text
    assert "1 gate unknown (FundamentalGate)" in text


def test_a_candidate_without_a_risk_assessment_reports_no_unknowns():
    assert unevaluable_gates(SimpleNamespace(risk_assessment=None)) == ()
    assert unevaluable_gates(None) == ()
