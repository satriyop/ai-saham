"""Present-only ADR-054 Judge stage for screen-accum board rows.

Default Enter path: no engine re-run, no network. Uses shared
``decision_display`` for Why / readiness / Accum breakdown / decision stack.

When ``row.source`` is missing (e.g. snapshot-restored board), render limited
judge scalars + explicit degradation banner — never invent READY.

Layer: Adapter (pure display)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.adapters.shared.decision_display import (
    coverage_pct,
    format_accum_breakdown,
    format_action_why,
    format_decision_stack,
    format_market_context_lines,
    format_primary_setup_family,
    format_setup_readiness,
    named_setup_match_glyphs,
    readiness_and_family,
)
from src.adapters.shared.score_display_labels import ACCUM, SIGNAL
from src.adapters.shared.screen_accum_board_fields import extract_screen_accum_board_fields
from src.adapters.tui.phase_sequence import (
    PhaseSequenceFact,
    format_phase_sequence_section,
)
from src.adapters.tui.presenters.accum_presenter import AccumRowView, build_accum_focus

# Product-facing degradation when board row has no candidate object.
LIMITED_JUDGE_BANNER = (
    "[#d4b06a]Limited judge[/]  snapshot / no candidate object · "
    "scalars only · [bold]j[/] re-judge local for full desk"
)

JUDGE_FOOTER_FULL = (
    "[dim]esc board · p plan · j re-judge local · Ctrl+P · present-only (same object as board)[/]"
)
JUDGE_FOOTER_LIMITED = (
    "[dim]esc board · p plan · j re-judge local · Ctrl+P · limited (no source)[/]"
)


@dataclass(frozen=True)
class AccumEngineInspectView:
    """Plain multi-section judge text for the detail stage."""

    text: str
    ticker: str
    limited: bool = False


def present_accum_engine_inspect(
    row: AccumRowView,
    *,
    rank: int = 1,
    total: int = 1,
    board_summary: str = "",
    effective_session: Any | None = None,
    market_context: Any | None = None,
    phase_sequence: Sequence[PhaseSequenceFact] | None = None,
    phase_sequence_unavailable: str | None = None,
) -> AccumEngineInspectView:
    """Build ADR-054 judge view from board row (present-only by default)."""
    source = getattr(row, "source", None)
    limited = source is None

    if source is not None:
        fields = extract_screen_accum_board_fields(source, phase_style="full")
        ticker = fields.ticker
        signal = fields.signal
        accum = fields.accum
        action = fields.action
        gate = fields.gate
        phase = fields.phase
    else:
        ticker = str(getattr(row, "ticker", "?") or "?")
        signal = str(getattr(row, "signal", "—") or "—")
        accum = str(getattr(row, "accum", "—") or "—")
        action = str(getattr(row, "action", "—") or "—")
        gate = str(getattr(row, "gate", "—") or "—")
        phase = str(getattr(row, "phase", "—") or "—")

    focus = build_accum_focus(row, rank=rank, total=total)
    if limited:
        why = ""
        breakdown = f"{accum} (no candidate · re-judge for breakdown)"
        family = "—"
        auth = "—"
        readiness_s = "— (no candidate object)"
    else:
        why = focus.why or format_action_why(source, gate=gate) or ""
        breakdown = format_accum_breakdown(source, accum_display=accum)
        family = format_primary_setup_family(source)
        cov = coverage_pct(source)
        auth = f"{cov:.0f}%" if cov is not None else "—"
        readiness, fam = readiness_and_family(source)
        readiness_s = format_setup_readiness(readiness, setup_family=fam, style="full")

    lines: list[str] = [
        f"[bold #e8e8e8]Judge · {ticker}[/]",
        f"Screen · accumulation · #{rank}/{total} by Signal",
    ]
    if board_summary:
        lines.append(f"[dim]Board[/]  {board_summary}")
    if limited:
        lines.append("")
        lines.append(LIMITED_JUDGE_BANNER)
    lines.append("")
    lines.extend(
        _judgment_header(
            ticker=ticker,
            action=action,
            gate=gate,
            signal=signal,
            accum=accum,
            phase=phase,
            family=family,
            authority=auth,
            why=why or "—",
            readiness=readiness_s,
            breakdown=breakdown,
        )
    )
    lines.append("")
    # ADR-058 production sequence memory (read-only; never re-scores Action).
    lines.extend(
        format_phase_sequence_section(
            phase_sequence,
            current_phase=phase,
            unavailable_reason=phase_sequence_unavailable,
        )
    )
    lines.append("")
    if limited:
        lines.extend(
            [
                "[#d4b06a]Decision[/]",
                f"  Action {action} · Gate {gate}",
                f"  ← Signal {signal} · coverage — · strength —",
                "  ← Risk —",
                "  ← Why: — (re-judge for full Why)",
            ]
        )
    else:
        lines.extend(
            format_decision_stack(
                source,
                action=action,
                gate=gate,
                signal=signal,
                why=why,
            )
        )
    lines.append("")
    if not limited:
        lines.extend(_section_named_setups(source))
        lines.append("")
        lines.extend(_section_signal(source))
        lines.append("")
        lines.extend(_section_risk(source))
        lines.append("")
        lines.extend(_section_trade_setup(source, action=action))
        lines.append("")
        lines.extend(_section_accum(accum, breakdown))
        lines.append("")
        lines.extend(_section_data(source, lag=focus.lag_label))
        lines.append("")
        lines.extend(_section_session(effective_session))
        lines.append("")
        lines.extend(format_market_context_lines(market_context, candidate=source))
        lines.append("")
        lines.append(JUDGE_FOOTER_FULL)
    else:
        lines.extend(
            [
                "[#9b8fb8]Scalars (board row)[/]",
                f"  phase {phase} · streak {getattr(row, 'streak', '—')} · "
                f"rsi {getattr(row, 'rsi', '—')} · net {getattr(row, 'net_pct', '—')}",
                f"  disc {getattr(row, 'disc_pct', '—')} · px {getattr(row, 'price', '—')}",
                "",
                "[#9b8fb8]Signal / Risk / TradeSetup[/]",
                "  not available without candidate object — press [bold]j[/] re-judge",
                "",
                JUDGE_FOOTER_LIMITED,
            ]
        )

    return AccumEngineInspectView(text="\n".join(lines), ticker=ticker, limited=limited)


# ADR-054 product alias (same function).
present_accum_judge = present_accum_engine_inspect


def _judgment_header(
    *,
    ticker: str,
    action: str,
    gate: str,
    signal: str,
    accum: str,
    phase: str,
    family: str,
    authority: str,
    why: str,
    readiness: str,
    breakdown: str,
) -> list[str]:
    """CLI-parity judgment strip fields (text form)."""
    return [
        "[#d4b06a]Judgment[/]",
        f"  Ticker     {ticker}",
        f"  Action     {action}",
        f"  Gate       {gate}",
        f"  {SIGNAL:<10} {signal}",
        f"  {ACCUM:<10} {accum}",
        f"  Authority  {authority}",
        f"  Phase      {phase}",
        f"  Family     {family}",
        f"  Why        {why}",
        f"  Readiness  {readiness}",
        f"  Accum brk  {breakdown}",
    ]


def _section_named_setups(source: Any) -> list[str]:
    lines = ["[#9b8fb8]Named setups (diagnostic)[/]"]
    if source is None:
        lines.append("  —")
        return lines
    family = format_primary_setup_family(source)
    glyphs = named_setup_match_glyphs(source)
    if family == "—" and not any(v not in {"-", "—", ""} for v in glyphs.values()):
        lines.append("  not evaluated on this candidate")
        return lines
    lines.append(f"  primary {family}")
    g = " · ".join(f"{k} {glyphs.get(k, '-')}" for k in ("FB", "CS", "SM", "PB"))
    lines.append(f"  match {g}")
    lines.append("  [dim]MATCH ≠ ENTER[/]")
    return lines


def _section_signal(source: Any) -> list[str]:
    lines = ["[#9b8fb8]Signal[/]"]
    sa = getattr(source, "signal_assessment", None) if source is not None else None
    if sa is None:
        lines.append("  not available on this candidate")
        return lines

    assessment = getattr(sa, "assessment", None)
    if assessment is not None:
        score = getattr(assessment, "score", None)
        strength = getattr(assessment, "strength", None)
        eq = getattr(assessment, "entry_quality", None)
    else:
        score = getattr(sa, "score", None)
        strength = getattr(sa, "strength", None)
        eq = getattr(sa, "entry_quality", None)
    strength_s = str(getattr(strength, "value", strength) or "—")
    eq_s = str(getattr(eq, "value", eq) or "—")

    cov = None
    if assessment is not None:
        cov = getattr(assessment, "signal_authority_coverage", None)
    if cov is None:
        cov = getattr(sa, "signal_authority_coverage", None)
    cov_s = _fmt_coverage(cov)

    lines.append(f"  score {score if score is not None else '—'} · strength {strength_s}")
    lines.append(f"  entry_quality {eq_s} · coverage {cov_s}")

    warn = getattr(sa, "coverage_warning", None)
    if warn:
        lines.append(f"  warning: {warn}")

    breakdown = None
    if assessment is not None:
        breakdown = getattr(assessment, "breakdown", None) or getattr(
            assessment, "breakdown_dict", None
        )
    if breakdown:
        if isinstance(breakdown, dict):
            parts = [f"{k}={v}" for k, v in breakdown.items()]
        else:
            parts = [f"{k}={v}" for k, v in breakdown]
        lines.append(f"  groups: {', '.join(parts)}")

    readiness, family = readiness_and_family(source)
    lines.append(
        "  setup readiness: " + format_setup_readiness(readiness, setup_family=family, style="full")
    )

    constraints = getattr(assessment, "decision_constraints", None) if assessment else None
    if constraints is not None:
        max_d = getattr(constraints, "max_decision", None)
        lines.append(f"  constraints max_decision: {max_d if max_d is not None else '—'}")
        reasons = getattr(constraints, "constraint_reasons", None) or ()
        for r in list(reasons)[:6]:
            lines.append(f"    · {r}")
    return lines


def _section_risk(source: Any) -> list[str]:
    lines = ["[#9b8fb8]Risk[/]"]
    risk = getattr(source, "risk_assessment", None) if source is not None else None
    if risk is None:
        lines.append("  not available on this candidate")
        return lines

    verdict = getattr(risk, "risk_level_name", None)
    if verdict is None:
        triggered = getattr(risk, "gate_triggered", None)
        verdict = "BLOCKED" if triggered else "OPEN"
    lines.append(f"  verdict {verdict}")

    rat = getattr(risk, "rationale", None) or ()
    if rat:
        if isinstance(rat, (list, tuple)):
            lines.append(f"  rationale: {'; '.join(str(x) for x in rat)}")
        else:
            lines.append(f"  rationale: {rat}")

    gates = getattr(source, "risk_gate_evaluations", None) or ()
    if not gates:
        lines.append("  gates: —")
        return lines
    lines.append("  gates:")
    for g in gates:
        name = getattr(g, "gate", "?")
        outcome = getattr(g, "outcome", "—")
        trig = getattr(g, "triggered", False)
        reason = getattr(g, "reason", "") or ""
        flag = " triggered" if trig else ""
        lines.append(f"    {name} {outcome}{flag} · {reason}")
    return lines


def _section_trade_setup(source: Any, *, action: str) -> list[str]:
    lines = ["[#9b8fb8]TradeSetup[/]"]
    ts = getattr(source, "trade_setup", None) if source is not None else None
    if ts is None:
        lines.append("  not available on this candidate")
        return lines

    act = getattr(ts, "action", None)
    act_s = str(getattr(act, "short", None) or getattr(act, "value", act) or action)
    sig = getattr(ts, "signal_score", None)
    strength = getattr(ts, "signal_strength", None)
    strength_s = str(getattr(strength, "value", strength) or "—")
    sig_s = sig if sig is not None else "—"
    lines.append(f"  action {act_s} · signal_score {sig_s} · {strength_s}")
    rationale = getattr(ts, "rationale", None)
    if rationale:
        lines.append(f"  rationale: {rationale}")
    blocking = getattr(ts, "blocking_gates", None) or ()
    if blocking:
        lines.append(f"  blocking_gates: {', '.join(str(b) for b in blocking)}")
    return lines


def _section_accum(accum: str, breakdown: str) -> list[str]:
    return [
        "[#9b8fb8]Accum (screen)[/]",
        f"  total {accum}",
        f"  breakdown: {breakdown}",
    ]


def _section_data(source: Any, *, lag: str) -> list[str]:
    lines = ["[#9b8fb8]Data[/]"]
    if source is None:
        lines.append("  —")
        return lines
    fr = getattr(source, "freshness", None)
    candle = getattr(source, "latest_candle_date", None)
    broker = getattr(source, "latest_broker_date", None)
    if fr is not None:
        candle = getattr(fr, "candle_as_of", None) or candle
        broker = getattr(fr, "broker_as_of", None) or broker
        align = getattr(fr, "alignment_state", None)
        align_s = str(getattr(align, "value", align) or "—")
        c_state = getattr(fr, "candle_state", None)
        b_state = getattr(fr, "broker_state", None)
        lines.append(f"  align {align_s}")
        lines.append(
            f"  candle {candle} ({getattr(c_state, 'value', c_state) or '—'}) · "
            f"broker {broker} ({getattr(b_state, 'value', b_state) or '—'})"
        )
    else:
        c_s = candle if candle is not None else "—"
        b_s = broker if broker is not None else "—"
        lines.append(f"  candle {c_s} · broker {b_s}")
    if lag and lag != "—":
        lines.append(f"  lag {lag}")
    return lines


def _section_session(effective_session: Any | None) -> list[str]:
    lines = ["[#9b8fb8]Session[/]"]
    if effective_session is None:
        lines.append("  —")
        return lines
    name = getattr(effective_session, "market_session_name", None)
    as_of = getattr(effective_session, "analysis_as_of", None)
    latest = getattr(effective_session, "latest_completed_session", None)
    src = getattr(effective_session, "resolution_source", None)
    name_s = name if name is not None else "—"
    as_of_s = as_of if as_of is not None else "—"
    latest_s = latest if latest is not None else "—"
    lines.append(f"  market_session {name_s}")
    lines.append(f"  analysis_as_of {as_of_s} · latest_completed {latest_s}")
    if src:
        lines.append(f"  resolution {src}")
    return lines


def _fmt_coverage(raw: Any) -> str:
    if raw is None:
        return "—"
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return "—"
    if val <= 1.0:
        val *= 100.0
    return f"{val:.0f}%"
