"""Shared decision display formatters for screen-accum (CLI + TUI).

Owns Why / setup readiness / Accum breakdown / decision-stack strings so
focus strip, Enter inspect, and plan confirm cannot diverge.

Present-only: no scoring, no IO, no Textual widgets.

Layer: Adapter (shared display)
"""

from __future__ import annotations

from typing import Any, Literal

ReadinessStyle = Literal["full", "why"]


def format_accum_breakdown(candidate: Any, *, accum_display: str = "") -> str:
    """Accum total as sum of component points (AccumScoreBreakdown)."""
    if not accum_display and candidate is not None:
        raw = getattr(candidate, "accum_score", None)
        accum_display = f"{float(raw):.1f}" if isinstance(raw, (int, float)) else "—"
    if candidate is None:
        return f"{accum_display} (no breakdown)"
    bd = getattr(candidate, "accum_score_breakdown", None)
    if bd is None:
        return f"{accum_display} (no breakdown)"
    parts: list[str] = []
    for comp in getattr(bd, "components", ()) or ():
        key = getattr(comp, "key", "?")
        status = getattr(comp, "status", None)
        status_s = str(getattr(status, "value", status) or "")
        if status_s == "DISABLED":
            parts.append(f"{key} off")
            continue
        if status_s == "MISSING":
            parts.append(f"{key} miss")
            continue
        pts = getattr(comp, "score_points", None)
        if pts is None:
            parts.append(f"{key} —")
        else:
            parts.append(f"{key} {float(pts):.1f}")
    if not parts:
        return f"{accum_display}"
    return f"{accum_display} = " + " + ".join(parts)


def format_setup_readiness(
    readiness: Any,
    *,
    setup_family: str | None = None,
    style: ReadinessStyle = "full",
) -> str:
    """Honest setup-readiness phrase (never invent READY).

    Code-truth cases:

    - readiness is None and no family → flow-only discovery (readiness N/A)
    - readiness is None and family set → defect (evaluator should have run)
    - readiness VO READY → shown in full style only (why style stays silent)
    - readiness VO non-READY → status + missing/failed inputs

    Screen batch often has family=None and readiness=None by design (no
    SetupEvidence on canonical flow). That is not a bug.
    """
    family = setup_family or _family_from_readiness(readiness)

    if readiness is None:
        if family:
            phrase = f"setup readiness missing for family [{family}] (defect)"
            return phrase if style == "full" else phrase
        # Flow-only: full explains; why stays quiet to avoid noise on every row
        if style == "full":
            return "flow-only (setup readiness not applicable)"
        return ""

    status = getattr(readiness, "status", None)
    status_s = str(getattr(status, "value", status) or "").upper()
    if not status_s:
        if style == "full":
            return "setup readiness present but status unset"
        return ""

    family = family or _family_from_readiness(readiness)
    family_s = f" [{family}]" if family else ""
    missing = tuple(getattr(readiness, "missing_required_inputs", ()) or ())
    failed = tuple(getattr(readiness, "failed_requirements", ()) or ())

    if status_s == "READY":
        # Do not invent READY elsewhere; only surface when the VO says so.
        return f"setup readiness READY{family_s}" if style == "full" else ""

    if status_s == "UNAVAILABLE":
        if missing:
            miss = ", ".join(str(m) for m in missing[:5])
            if len(missing) > 5:
                miss += ", …"
            return f"setup readiness UNAVAILABLE{family_s} (missing: {miss})"
        return f"setup readiness UNAVAILABLE{family_s}"

    if status_s == "INCOMPLETE":
        if failed:
            fail = ", ".join(str(f) for f in failed[:4])
            return f"setup readiness INCOMPLETE{family_s} ({fail})"
        return f"setup readiness INCOMPLETE{family_s}"

    if status_s == "INELIGIBLE":
        if failed:
            fail = ", ".join(str(f) for f in failed[:4])
            return f"setup readiness INELIGIBLE{family_s} ({fail})"
        phase = getattr(readiness, "current_phase", None)
        phase_s = getattr(phase, "value", phase) if phase is not None else None
        if phase_s:
            return f"setup readiness INELIGIBLE{family_s} (phase {phase_s})"
        return f"setup readiness INELIGIBLE{family_s}"

    return f"setup readiness {status_s}{family_s}"


def format_action_why(candidate: Any, *, gate: str = "") -> str:
    """Why Action is not a clean enter despite scores/gates (present-only)."""
    if candidate is None:
        return ""
    bits: list[str] = []

    cov = coverage_pct(candidate)
    if cov is not None:
        if cov < 70.0:
            bits.append(f"authority {cov:.0f}% (<70%)")
        else:
            bits.append(f"authority {cov:.0f}%")

    readiness, family = readiness_and_family(candidate)
    readiness_bit = format_setup_readiness(
        readiness,
        setup_family=family,
        style="why",
    )
    if readiness_bit:
        bits.append(readiness_bit)

    sa = getattr(candidate, "signal_assessment", None)
    assessment = getattr(sa, "assessment", None) if sa is not None else None
    constraints = getattr(assessment, "decision_constraints", None) if assessment else None
    if constraints is not None:
        for reason in getattr(constraints, "constraint_reasons", ()) or ():
            text = str(reason)
            low = text.lower()
            if "signal_authority_coverage" in low or "authority_coverage" in low:
                if not any(b.startswith("authority") for b in bits):
                    bits.append("authority thin")
                continue
            if "setup readiness" in low or "setup_readiness" in low:
                if not any(b.startswith("setup readiness") for b in bits):
                    bits.append(_fallback_setup_readiness_phrase(text))
                continue
            if text and text not in bits:
                bits.append(text if len(text) < 52 else text[:49] + "…")

    gate_s = str(gate or "")
    if gate_s == "BLOCKED":
        risk = getattr(candidate, "risk_assessment", None)
        which = getattr(risk, "gate_triggered", None) if risk else None
        bits.append(f"gate blocked ({which})" if which else "gate blocked")
    elif gate_s == "OPEN":
        bits.append("gate open")

    if not bits:
        ts = getattr(candidate, "trade_setup", None)
        rat = getattr(ts, "rationale", None) if ts else None
        if rat:
            return str(rat)[:80]
        return "no constraint detail"
    return " · ".join(bits)


def format_decision_stack(
    candidate: Any,
    *,
    action: str,
    gate: str,
    signal: str,
    why: str = "",
) -> list[str]:
    """Compact Decision header lines for Enter inspect (no new scores)."""
    lines = ["[#d4b06a]Decision[/]"]
    lines.append(f"  Action {action} · Gate {gate}")

    cov = coverage_pct(candidate)
    cov_s = f"{cov:.0f}%" if cov is not None else "—"
    strength_s = _strength_label(candidate)
    lines.append(f"  ← Signal {signal} · coverage {cov_s} · strength {strength_s}")

    risk_s = _risk_verdict(candidate)
    lines.append(f"  ← Risk {risk_s}")

    why_s = why or format_action_why(candidate, gate=gate) or "—"
    lines.append(f"  ← Why: {why_s}")
    return lines


def format_market_context_lines(
    market_context: Any | None,
    *,
    candidate: Any = None,
) -> list[str]:
    """Market context section lines (display-only; never invent regime scores)."""
    lines = ["[#9b8fb8]Market context[/]"]
    mc = market_context
    if mc is None and candidate is not None:
        mc = getattr(candidate, "market_context", None)

    if mc is not None:
        regime = getattr(mc, "regime", None)
        regime_s = str(getattr(regime, "value", regime) or regime or "—")
        lines.append(f"  regime {regime_s}")
        conv = getattr(mc, "conviction", None)
        if isinstance(conv, (int, float)):
            lines.append(f"  conviction {float(conv):.2f}")
        conf = getattr(mc, "regime_confidence", None)
        if isinstance(conf, (int, float)):
            lines.append(f"  confidence {float(conf):.2f}")
        stab = getattr(mc, "regime_stability", None)
        if stab:
            lines.append(f"  stability {stab}")
        days = getattr(mc, "days_in_regime", None)
        if days is not None:
            lines.append(f"  days_in_regime {days}")
        for warn_attr in ("staleness_warning", "coverage_warning", "transition_warning"):
            w = getattr(mc, warn_attr, None)
            if w:
                lines.append(f"  warning: {w}")
        return lines

    # Fallback: regime only if already on decision constraints (do not invent MCE)
    sa = getattr(candidate, "signal_assessment", None) if candidate is not None else None
    assessment = getattr(sa, "assessment", None) if sa is not None else None
    constraints = getattr(assessment, "decision_constraints", None) if assessment else None
    regime = getattr(constraints, "regime", None) if constraints else None
    if regime is not None:
        lines.append(f"  regime (from decision constraints) {regime}")
        lines.append("  [dim]full MarketContext not on this screen run[/]")
    else:
        lines.append("  not evaluated for this screen run")
    return lines


# Stable column order for screen pattern-match boards (matches AVAILABLE_SWING_SETUPS).
NAMED_SETUP_BOARD_ORDER: tuple[str, ...] = (
    "foreign-bounce",
    "coiled-spring",
    "smart-money-confirmed",
    "pullback-continuation",
)
NAMED_SETUP_SHORT_LABELS: dict[str, str] = {
    "foreign-bounce": "FB",
    "coiled-spring": "CS",
    "smart-money-confirmed": "SM",
    "pullback-continuation": "PB",
}
_MATCH_GLYPH: dict[str, str] = {
    "MATCH": "M",
    "PARTIAL": "~",
    "NO_MATCH": "·",
}


def readiness_and_family(candidate: Any) -> tuple[Any, str | None]:
    """Extract setup_readiness VO and family from a screen candidate."""
    if candidate is None:
        return None, None
    sa = getattr(candidate, "signal_assessment", None)
    assessment = getattr(sa, "assessment", None) if sa is not None else None
    readiness = getattr(assessment, "setup_readiness", None) if assessment else None
    if readiness is None and sa is not None:
        readiness = getattr(sa, "setup_readiness", None)

    family = _family_from_readiness(readiness)
    if not family:
        family = getattr(candidate, "setup_family", None) or None
    if not family:
        sfr = getattr(candidate, "setup_family_result", None)
        if sfr is not None:
            family = getattr(sfr, "primary_setup_family", None) or None
    if family is not None:
        family = str(family) or None
    return readiness, family


def named_setup_match_glyphs(candidate: Any) -> dict[str, str]:
    """Compact MATCH/PARTIAL/NO_MATCH glyphs per named setup (diagnostic only).

    Returns short-label → glyph. Missing evals render as ``-`` (not evaluated).
    Glyphs: M=MATCH, ~=PARTIAL, ·=NO_MATCH. Does not grant entry authority.
    """
    evals = getattr(candidate, "named_setup_evaluations", None) or {}
    out: dict[str, str] = {}
    for name in NAMED_SETUP_BOARD_ORDER:
        short = NAMED_SETUP_SHORT_LABELS.get(name, name[:2].upper())
        evaluation = evals.get(name) if isinstance(evals, dict) else None
        if evaluation is None:
            out[short] = "-"
            continue
        match = getattr(evaluation, "match", None)
        match_s = str(getattr(match, "value", match) or "")
        out[short] = _MATCH_GLYPH.get(match_s, "?")
    return out


def format_primary_setup_family(candidate: Any) -> str:
    """Primary setup family label for boards; ``-`` when unresolved."""
    _, family = readiness_and_family(candidate)
    if family:
        return str(family)
    sfr = getattr(candidate, "setup_family_result", None) if candidate is not None else None
    if sfr is not None:
        primary = getattr(sfr, "primary_setup_family", None)
        if primary:
            return str(primary)
    return "-"


def coverage_pct(candidate: Any) -> float | None:
    """Signal authority coverage as 0–100 percentage, if present."""
    sa = getattr(candidate, "signal_assessment", None)
    if sa is None:
        return None
    assessment = getattr(sa, "assessment", None)
    raw = None
    if assessment is not None:
        raw = getattr(assessment, "signal_authority_coverage", None)
    if raw is None:
        raw = getattr(sa, "signal_authority_coverage", None)
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val * 100.0 if val <= 1.0 else val
    return None


def _family_from_readiness(readiness: Any) -> str | None:
    if readiness is None:
        return None
    family = getattr(readiness, "setup_family", None)
    if family is None:
        return None
    s = str(family)
    return s or None


def _fallback_setup_readiness_phrase(constraint_text: str) -> str:
    """When VO is missing, compress constraint string without inventing inputs."""
    low = constraint_text.lower()
    if "unavailable" in low:
        return "setup readiness UNAVAILABLE"
    if "incomplete" in low:
        return "setup readiness INCOMPLETE"
    if "ineligible" in low:
        return "setup readiness INELIGIBLE"
    return constraint_text if len(constraint_text) < 52 else constraint_text[:49] + "…"


def _strength_label(candidate: Any) -> str:
    sa = getattr(candidate, "signal_assessment", None) if candidate is not None else None
    assessment = getattr(sa, "assessment", None) if sa is not None else None
    strength = None
    if assessment is not None:
        strength = getattr(assessment, "strength", None)
    if strength is None and sa is not None:
        strength = getattr(sa, "strength", None)
    if strength is None:
        ts = getattr(candidate, "trade_setup", None) if candidate is not None else None
        strength = getattr(ts, "signal_strength", None) if ts else None
    return str(getattr(strength, "value", strength) or "—")


def _risk_verdict(candidate: Any) -> str:
    risk = getattr(candidate, "risk_assessment", None) if candidate is not None else None
    if risk is None:
        return "—"
    verdict = getattr(risk, "risk_level_name", None)
    if verdict is not None:
        return str(verdict)
    triggered = getattr(risk, "gate_triggered", None)
    return "BLOCKED" if triggered else "OPEN"
