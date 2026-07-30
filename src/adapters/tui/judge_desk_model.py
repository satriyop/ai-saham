"""Structured Judge desk model for widget + text presenters (ADR-054).

Present-only: no re-score. Built from board row + optional phase ledger facts.

Layer: Adapter
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
    readiness_and_family,
)
from src.adapters.shared.screen_accum_board_fields import extract_screen_accum_board_fields
from src.adapters.tui.phase_sequence import PhaseSequenceFact, format_phase_sequence_section
from src.adapters.tui.presenters.accum_presenter import AccumRowView, build_accum_focus


@dataclass(frozen=True)
class JudgeScoreCell:
    label: str
    value: str


@dataclass(frozen=True)
class JudgeDeskModel:
    """Everything the Verdict-mast widget needs to paint (no IO)."""

    ticker: str
    limited: bool
    rank: int
    total: int
    board_summary: str
    action: str
    gate: str
    signal: str
    accum: str
    authority: str
    family: str
    phase: str
    readiness: str
    why: str
    breakdown: str
    scores: tuple[JudgeScoreCell, ...]
    phase_section_title: str
    phase_arrow: str
    phase_detail_lines: tuple[str, ...]
    phase_footer: str
    decision_lines: tuple[str, ...]
    cards: tuple[tuple[str, tuple[str, ...]], ...]  # (title, body lines)
    footer: str


def build_judge_desk_model(
    row: AccumRowView,
    *,
    rank: int = 1,
    total: int = 1,
    board_summary: str = "",
    effective_session: Any | None = None,
    market_context: Any | None = None,
    phase_sequence: Sequence[PhaseSequenceFact] | None = None,
    phase_sequence_unavailable: str | None = None,
) -> JudgeDeskModel:
    """Pure build of Judge desk model from board row + ledger facts."""
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
        why = "—"
        breakdown = f"{accum} (no candidate · re-judge for breakdown)"
        family = "—"
        auth = "—"
        readiness_s = "— (no candidate object)"
    else:
        why = focus.why or format_action_why(source, gate=gate) or "—"
        breakdown = format_accum_breakdown(source, accum_display=accum)
        family = format_primary_setup_family(source)
        cov = coverage_pct(source)
        auth = f"{cov:.0f}%" if cov is not None else "—"
        readiness, fam = readiness_and_family(source)
        readiness_s = format_setup_readiness(readiness, setup_family=fam, style="full")

    scores = (
        JudgeScoreCell("Signal", signal),
        JudgeScoreCell("Accum", accum),
        JudgeScoreCell("Authority", auth),
        JudgeScoreCell("Family", family if family != "—" else "—"),
        JudgeScoreCell("Phase", phase),
        JudgeScoreCell("Ready", readiness_s[:24] if len(readiness_s) > 24 else readiness_s),
    )

    phase_lines = format_phase_sequence_section(
        phase_sequence,
        current_phase=phase,
        unavailable_reason=phase_sequence_unavailable,
    )
    # Parse structured pieces for widget (skip markup title line)
    phase_title = "Phase sequence · ledger"
    phase_arrow = ""
    phase_details: list[str] = []
    phase_footer = "production memory · not a re-score"
    for line in phase_lines[1:]:
        plain = _strip_markup(line).strip()
        if not plain:
            continue
        if "→" in plain and not plain.startswith("·") and not plain.startswith("now"):
            phase_arrow = plain
        elif plain.startswith("·") or plain.startswith("now") or plain.startswith("["):
            if "production memory" in plain or "not a re-score" in plain:
                phase_footer = plain
            else:
                phase_details.append(plain.lstrip("· ").strip() if plain.startswith("·") else plain)
        elif "no closed-session" in plain or "cannot load" in plain or "not wired" in plain:
            phase_arrow = plain
        else:
            phase_details.append(plain)

    if limited:
        decision_lines = (
            f"Action {action} · Gate {gate}",
            f"← Signal {signal} · coverage — · strength —",
            "← Risk —",
            "← Why: — (re-judge for full Why)",
        )
        cards: list[tuple[str, tuple[str, ...]]] = (
            (
                "Scalars (board row)",
                (
                    f"phase {phase} · streak {getattr(row, 'streak', '—')} · "
                    f"rsi {getattr(row, 'rsi', '—')} · net {getattr(row, 'net_pct', '—')}",
                    f"disc {getattr(row, 'disc_pct', '—')} · px {getattr(row, 'price', '—')}",
                    "Signal / Risk / TradeSetup unavailable — press j re-judge",
                ),
            ),
        )
        footer = "esc board · p plan · j re-judge · r live · limited (no source)"
    else:
        stack = format_decision_stack(
            source,
            action=action,
            gate=gate,
            signal=signal,
            why=why if why != "—" else "",
        )
        decision_lines = tuple(_strip_markup(x) for x in stack if _strip_markup(x).strip())
        cards = _full_cards(
            source=source,
            action=action,
            accum=accum,
            breakdown=breakdown,
            lag=focus.lag_label,
            effective_session=effective_session,
            market_context=market_context,
        )
        footer = "esc board · p plan · j re-judge · present-only · Verdict mast"

    return JudgeDeskModel(
        ticker=ticker,
        limited=limited,
        rank=rank,
        total=total,
        board_summary=board_summary or "",
        action=action,
        gate=gate,
        signal=signal,
        accum=accum,
        authority=auth,
        family=family,
        phase=phase,
        readiness=readiness_s,
        why=why,
        breakdown=breakdown,
        scores=scores,
        phase_section_title=phase_title,
        phase_arrow=phase_arrow,
        phase_detail_lines=tuple(phase_details),
        phase_footer=phase_footer,
        decision_lines=decision_lines,
        cards=cards,
        footer=footer,
    )


def _full_cards(
    *,
    source: Any,
    action: str,
    accum: str,
    breakdown: str,
    lag: str,
    effective_session: Any | None,
    market_context: Any | None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    from src.adapters.tui.presenters.accum_engine_inspect_presenter import (
        _section_accum,
        _section_data,
        _section_named_setups,
        _section_risk,
        _section_session,
        _section_signal,
        _section_trade_setup,
    )

    def _card(lines: list[str]) -> tuple[str, tuple[str, ...]]:
        title = _strip_markup(lines[0]) if lines else "—"
        # strip section color markers like "Named setups..."
        title = title.replace("[#9b8fb8]", "").replace("[/]", "").strip()
        body = tuple(_strip_markup(x).strip() for x in lines[1:] if _strip_markup(x).strip())
        return title, body

    cards: list[tuple[str, tuple[str, ...]]] = [
        _card(_section_named_setups(source)),
        _card(_section_signal(source)),
        _card(_section_risk(source)),
        _card(_section_trade_setup(source, action=action)),
        _card(_section_accum(accum, breakdown)),
        _card(_section_data(source, lag=lag)),
        _card(_section_session(effective_session)),
    ]
    mce = format_market_context_lines(market_context, candidate=source)
    if mce:
        cards.append(_card(list(mce)))
    return tuple(cards)


def _strip_markup(s: str) -> str:
    """Remove simple Textual/Rich style tags for plain widget paint."""
    import re

    return re.sub(r"\[/?[^\]]*\]", "", s or "")


def action_css_class(action: str) -> str:
    a = (action or "").strip().upper()
    if a in {"ENTER", "BUY"}:
        return "action-enter"
    if a in {"AVOID", "BLOCK", "SELL"}:
        return "action-avoid"
    if a in {"WATCH", "HOLD"}:
        return "action-watch"
    return "action-other"


def gate_css_class(gate: str) -> str:
    g = (gate or "").strip().upper()
    if g in {"OPEN", "PASS", "CLEAR"}:
        return "gate-open"
    if g in {"BLOCK", "BLOCKED", "FAIL", "CLOSED"}:
        return "gate-block"
    return "gate-other"
