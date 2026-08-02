"""Structured Judge desk model for widget + text presenters (ADR-054).

Present-only: no re-score. Built from board row + optional phase ledger facts.
Lower sections are compact **cards** (design: tui-judge-desk.html), not a diary dump.

Layer: Adapter
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.adapters.shared.decision_display import (
    coverage_pct,
    format_action_why,
    format_decision_stack,
    format_primary_setup_family,
    format_setup_readiness,
    named_setup_match_glyphs,
    readiness_and_family,
)
from src.adapters.shared.screen_accum_board_fields import extract_screen_accum_board_fields
from src.adapters.shared.trade_action_labels import (
    ACTION_AVOID,
    ACTION_BLOCK,
    ACTION_ENTER,
    ACTION_WATCH,
    AVOID_LIKE,
    ENTER_LIKE,
    WATCH_LIKE,
)
from src.adapters.tui.phase_sequence import PhaseSequenceFact, format_phase_sequence_section
from src.adapters.tui.presenters.accum_presenter import AccumRowView, build_accum_focus

# Stable card keys for widget slots (order = paint order).
CARD_RISK = "risk"
CARD_TRADE_SETUP = "trade_setup"
CARD_ACCUM = "accum"
CARD_DATA = "data"
CARD_SESSION = "session"
CARD_MARKET = "market"
CARD_NAMED = "named_setups"
CARD_SIGNAL = "signal"
CARD_SCALARS = "scalars"

# Full-source default grid order (2-col rows).
CARD_ORDER_FULL: tuple[str, ...] = (
    CARD_RISK,
    CARD_TRADE_SETUP,
    CARD_ACCUM,
    CARD_DATA,
    CARD_SESSION,
    CARD_MARKET,
    CARD_NAMED,
    CARD_SIGNAL,
)


@dataclass(frozen=True)
class JudgeScoreCell:
    label: str
    value: str


@dataclass(frozen=True)
class JudgeCard:
    """One bordered card on the Judge desk.

    ``tone`` drives a thin accent (open / block / watch / neutral).
    ``lines`` prefer short k/v or chip rows — never gate essays.
    """

    key: str
    title: str
    headline: str
    lines: tuple[str, ...] = ()
    tone: str = "neutral"  # open | block | watch | neutral


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
    cards: tuple[JudgeCard, ...]
    footer: str

    def card_by_key(self, key: str) -> JudgeCard | None:
        for c in self.cards:
            if c.key == key:
                return c
        return None


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
        from src.adapters.shared.decision_display import format_accum_breakdown

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
        JudgeScoreCell("Ready", _score_ready_label(readiness_s)),
    )

    phase_lines = format_phase_sequence_section(
        phase_sequence,
        current_phase=phase,
        unavailable_reason=phase_sequence_unavailable,
    )
    phase_title = "Phase sequence · ledger"
    phase_arrow = ""
    phase_details: list[str] = []
    phase_footer = "production memory · not a re-score"
    for line in phase_lines[1:]:
        plain = _strip_markup(line).strip()
        if not plain:
            continue
        if "→" in plain and not plain.startswith("·") and "now" not in plain[:6]:
            if "only" in plain.lower() or plain.count("→") >= 1:
                phase_arrow = plain
        elif "production memory" in plain or "not a re-score" in plain:
            phase_footer = plain
        elif plain.startswith("·") or "sessions" in plain.lower():
            phase_details.append(plain.lstrip("· ").strip())
        elif plain.startswith("now") or plain.startswith("["):
            if "production memory" not in plain:
                phase_details.append(plain)
        elif "no closed-session" in plain or "cannot load" in plain or "not wired" in plain:
            phase_arrow = plain
        elif "transition" in plain.lower():
            phase_details.append(plain)
        else:
            if not phase_arrow and ("only" in plain.lower() or "→" in plain):
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
        cards = (
            JudgeCard(
                key=CARD_SCALARS,
                title="Scalars",
                headline=f"{action} · {gate}",
                lines=(
                    f"phase {phase} · streak {getattr(row, 'streak', '—')} · "
                    f"rsi {getattr(row, 'rsi', '—')}",
                    f"net {getattr(row, 'net_pct', '—')} · "
                    f"disc {getattr(row, 'disc_pct', '—')} · "
                    f"px {getattr(row, 'price', '—')}",
                    "full desk · j re-judge or r live",
                ),
                tone=_tone_from_action_gate(action, gate),
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
        # Compact decision: drop empty / tag-only lines; cap body length.
        decision_lines = tuple(
            _strip_markup(x).strip()
            for x in stack
            if _strip_markup(x).strip() and not _strip_markup(x).strip().startswith("[")
        )[:6]
        cards = _compact_cards(
            source=source,
            action=action,
            accum=accum,
            breakdown=breakdown,
            lag=focus.lag_label,
            effective_session=effective_session,
            market_context=market_context,
        )
        footer = "d detail · esc board · p plan · j re-judge · present-only · Verdict mast"

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
        phase_detail_lines=tuple(phase_details[:6]),
        phase_footer=phase_footer,
        decision_lines=decision_lines,
        cards=cards,
        footer=footer,
    )


def _score_ready_label(readiness_s: str) -> str:
    """Compact Ready cell for verdict score strip (no mid-word clip)."""
    s = (readiness_s or "—").strip() or "—"
    low = s.lower()
    if low.startswith("flow-only"):
        return "flow-only"
    if "not applicable" in low:
        return "n/a"
    if "no candidate" in low:
        return "no object"
    if "missing" in low and "defect" in low:
        return "missing"
    if len(s) <= 14:
        return s
    return s[:13] + "…"


def _compact_cards(
    *,
    source: Any,
    action: str,
    accum: str,
    breakdown: str,
    lag: str,
    effective_session: Any | None,
    market_context: Any | None,
) -> tuple[JudgeCard, ...]:
    """Design-dense cards: headline first, short secondary lines."""
    out: list[JudgeCard] = [
        _card_risk(source),
        _card_trade_setup(source, action=action),
        _card_accum(accum, breakdown),
        _card_data(source, lag=lag),
        _card_session(effective_session),
    ]
    mce = _card_market(market_context)
    if mce is not None:
        out.append(mce)
    named = _card_named_setups(source)
    if named is not None:
        out.append(named)
    sig = _card_signal(source)
    if sig is not None:
        out.append(sig)
    return tuple(out)


def _card_risk(source: Any) -> JudgeCard:
    risk = getattr(source, "risk_assessment", None)
    if risk is None:
        return JudgeCard(CARD_RISK, "Risk", "—", ("not available",), tone="neutral")

    verdict = getattr(risk, "risk_level_name", None)
    if verdict is None:
        triggered = getattr(risk, "gate_triggered", None)
        verdict = "BLOCKED" if triggered else "OPEN"
    verdict_s = str(verdict)

    rat = getattr(risk, "rationale", None) or ()
    if isinstance(rat, (list, tuple)):
        rat_s = "; ".join(str(x) for x in rat[:2])
    else:
        rat_s = str(rat)
    # One short summary line — never per-gate essays
    if len(rat_s) > 56:
        rat_s = rat_s[:53] + "…"

    gates = getattr(source, "risk_gate_evaluations", None) or ()
    chip_parts: list[str] = []
    blocked: list[str] = []
    for g in gates:
        name = str(getattr(g, "gate", "?") or "?")
        short = _gate_short(name)
        trig = bool(getattr(g, "triggered", False))
        outcome = str(getattr(g, "outcome", "") or "").lower()
        if trig or outcome in {"fail", "block", "blocked"}:
            blocked.append(short)
            chip_parts.append(f"✗{short}")
        else:
            chip_parts.append(f"✓{short}")

    tone = "block" if blocked or ACTION_BLOCK in verdict_s.upper() else "open"
    if blocked:
        chips = " ".join(chip_parts[:8]) if chip_parts else "—"
        lines = (rat_s or "blocked", chips)
        headline = f"{verdict_s} · blocked"
    elif chip_parts:
        chips = " ".join(chip_parts[:8])
        lines = (rat_s or "all gates passed", chips)
        headline = verdict_s
    else:
        lines = (rat_s or "no gate detail",)
        headline = verdict_s

    return JudgeCard(CARD_RISK, "Risk", headline, lines, tone=tone)


# Known risk gates → scannable chip labels (design-dense, not truncated words).
_GATE_CHIP: dict[str, str] = {
    "fundamental": "Fund",
    "liquidity": "Liq",
    "freefloat": "FF",
    "free_float": "FF",
    "bandar": "Bandar",
    "volatility": "Vol",
    "spread": "Spread",
    "concentration": "Conc",
    "drawdown": "DD",
    "correlation": "Corr",
}


def _gate_short(name: str) -> str:
    raw = name.replace("Gate", "").replace("gate", "").strip()
    key = re.sub(r"[^a-z0-9_]", "", raw.lower())
    if key in _GATE_CHIP:
        return _GATE_CHIP[key]
    if len(raw) <= 6:
        return raw
    parts = re.findall(r"[A-Z][a-z]*|[a-z]+", raw)
    if len(parts) >= 2:
        return "".join(p[0].upper() for p in parts[:3])
    return raw[:6]


def _card_trade_setup(source: Any, *, action: str) -> JudgeCard:
    ts = getattr(source, "trade_setup", None)
    if ts is None:
        return JudgeCard(
            CARD_TRADE_SETUP,
            "Trade setup",
            action or "—",
            ("not available",),
            tone="neutral",
        )

    act = getattr(ts, "action", None)
    act_s = str(getattr(act, "short", None) or getattr(act, "value", act) or action)
    sig = getattr(ts, "signal_score", None)
    strength = getattr(ts, "signal_strength", None)
    strength_s = str(getattr(strength, "value", strength) or "—")
    sig_s = str(sig) if sig is not None else "—"
    rationale = str(getattr(ts, "rationale", None) or "").strip()
    if len(rationale) > 56:
        rationale = rationale[:53] + "…"
    blocking = getattr(ts, "blocking_gates", None) or ()
    lines = [f"sig {sig_s} · {strength_s}"]
    if rationale and rationale not in lines[0]:
        lines.append(rationale)
    if blocking:
        lines.append("block " + ", ".join(str(b) for b in list(blocking)[:3]))
    return JudgeCard(
        CARD_TRADE_SETUP,
        "Trade setup",
        act_s,
        tuple(lines[:3]),
        tone=_tone_from_action_gate(act_s, ""),
    )


def _card_accum(accum: str, breakdown: str) -> JudgeCard:
    """Headline total; parts without long equation if possible."""
    parts = _parse_accum_parts(breakdown)
    if parts:
        # Two rows of up to 3 parts keeps the card scannable
        row1 = " · ".join(f"{k} {v}" for k, v in parts[:3])
        lines: list[str] = [row1]
        if len(parts) > 3:
            row2 = " · ".join(f"{k} {v}" for k, v in parts[3:6])
            if len(parts) > 6:
                row2 += " · …"
            lines.append(row2)
        return JudgeCard(CARD_ACCUM, "Accum", str(accum), tuple(lines), tone="neutral")
    br = breakdown or "—"
    if len(br) > 64:
        br = br[:61] + "…"
    return JudgeCard(CARD_ACCUM, "Accum", str(accum), (br,), tone="neutral")


def _parse_accum_parts(breakdown: str) -> list[tuple[str, str]]:
    """Extract name/value pairs from breakdown text when possible."""
    if not breakdown:
        return []
    found = re.findall(
        r"\b([a-zA-Z_]{2,12})\s*[=:]\s*([0-9.]+|off|—|-)",
        breakdown,
    )
    if found:
        return [(a, b) for a, b in found]
    found2 = re.findall(r"\b([a-zA-Z_]{2,12})\s+([0-9.]+|off)\b", breakdown)
    return [(a, b) for a, b in found2 if a.lower() not in {"total", "accum"}]


def _card_data(source: Any, *, lag: str) -> JudgeCard:
    fr = getattr(source, "freshness", None)
    candle = getattr(source, "latest_candle_date", None)
    broker = getattr(source, "latest_broker_date", None)
    align_s = "—"
    if fr is not None:
        candle = getattr(fr, "candle_as_of", None) or candle
        broker = getattr(fr, "broker_as_of", None) or broker
        align = getattr(fr, "alignment_state", None)
        align_s = str(getattr(align, "value", align) or "—")
    c_s = str(candle) if candle is not None else "—"
    b_s = str(broker) if broker is not None else "—"
    if len(c_s) > 10:
        c_s = c_s[:10]
    if len(b_s) > 10:
        b_s = b_s[:10]
    lines = [f"candle  {c_s}", f"broker  {b_s}"]
    if lag and lag != "—" and "ALIGNED" not in lag.upper():
        lines.append(lag[:56])
    tone = "open" if "ALIGN" in align_s.upper() else "watch"
    return JudgeCard(CARD_DATA, "Data", align_s, tuple(lines), tone=tone)


def _card_session(effective_session: Any | None) -> JudgeCard:
    if effective_session is None:
        return JudgeCard(CARD_SESSION, "Session", "—", ("no session",), tone="neutral")
    name = getattr(effective_session, "market_session_name", None) or "—"
    as_of = getattr(effective_session, "analysis_as_of", None)
    latest = getattr(effective_session, "latest_completed_session", None)
    as_of_s = str(as_of)[:10] if as_of is not None else "—"
    latest_s = str(latest)[:10] if latest is not None else "—"
    src = getattr(effective_session, "resolution_source", None)
    lines = [f"as_of  {as_of_s}", f"done   {latest_s}"]
    if src:
        src_s = str(src)
        if len(src_s) > 36:
            src_s = src_s[:33] + "…"
        lines.append(src_s)
    return JudgeCard(CARD_SESSION, "Session", str(name), tuple(lines), tone="neutral")


def _card_market(market_context: Any | None) -> JudgeCard | None:
    if market_context is None:
        return None
    regime = getattr(market_context, "regime", None)
    if regime is not None:
        regime_s = str(getattr(regime, "value", regime) or "—")
    else:
        regime_s = str(getattr(market_context, "regime_name", None) or "—")

    conv = getattr(market_context, "conviction", None)
    conf = getattr(market_context, "confidence", None)
    stab = getattr(market_context, "stability", None)
    stab_s = str(getattr(stab, "value", stab) or "—") if stab is not None else "—"
    warn = getattr(market_context, "warning", None) or getattr(
        market_context, "regime_warning", None
    )

    lines: list[str] = []
    bits = []
    if conv is not None:
        try:
            bits.append(f"conv {float(conv):.2f}")
        except (TypeError, ValueError):
            bits.append(f"conv {conv}")
    if conf is not None:
        try:
            bits.append(f"conf {float(conf):.2f}")
        except (TypeError, ValueError):
            bits.append(f"conf {conf}")
    if bits:
        lines.append(" · ".join(bits))
    if stab_s and stab_s != "—":
        lines.append(f"stab  {stab_s[:18]}")
    if warn:
        w = str(warn)
        if len(w) > 52:
            w = w[:49] + "…"
        lines.append(w)
    if not lines:
        from src.adapters.shared.decision_display import format_market_context_lines

        raw = format_market_context_lines(market_context, candidate=None)
        for ln in raw[1:4]:
            plain = _strip_markup(ln).strip()
            if plain:
                lines.append(plain[:56])
    tone = "watch" if "TRANS" in (stab_s or "").upper() or warn else "neutral"
    return JudgeCard(CARD_MARKET, "Market", regime_s, tuple(lines[:3]) or ("—",), tone=tone)


def _card_named_setups(source: Any) -> JudgeCard | None:
    family = format_primary_setup_family(source)
    glyphs = named_setup_match_glyphs(source)
    empty_family = family in {"—", "-", "", None}
    has_match = any(v not in {"-", "—", "", None} for v in glyphs.values())
    if empty_family and not has_match:
        return None
    g = " · ".join(f"{k} {glyphs.get(k, '-')}" for k in ("FB", "CS", "SM", "PB"))
    return JudgeCard(
        CARD_NAMED,
        "Named setups",
        "diagnostic" if empty_family else str(family),
        (g, f"MATCH ≠ {ACTION_ENTER}"),
        tone="neutral",
    )


def _card_signal(source: Any) -> JudgeCard | None:
    sa = getattr(source, "signal_assessment", None)
    if sa is None:
        return None
    assessment = getattr(sa, "assessment", None)
    if assessment is not None:
        score = getattr(assessment, "score", None)
        strength = getattr(assessment, "strength", None)
        eq = getattr(assessment, "entry_quality", None)
        cov = getattr(assessment, "signal_authority_coverage", None)
    else:
        score = getattr(sa, "score", None)
        strength = getattr(sa, "strength", None)
        eq = getattr(sa, "entry_quality", None)
        cov = getattr(sa, "signal_authority_coverage", None)
    if cov is None:
        cov = getattr(sa, "signal_authority_coverage", None)
    strength_s = str(getattr(strength, "value", strength) or "—")
    eq_s = str(getattr(eq, "value", eq) or "—")
    cov_s = "—"
    if cov is not None:
        try:
            v = float(cov)
            if v <= 1.0:
                v *= 100.0
            cov_s = f"{v:.0f}%"
        except (TypeError, ValueError):
            cov_s = str(cov)
    score_s = str(score) if score is not None else "—"
    warn = getattr(sa, "coverage_warning", None)
    lines = [f"entry  {eq_s}", f"cov    {cov_s}"]
    if warn:
        w = str(warn)
        lines.append(w[:52] + ("…" if len(w) > 52 else ""))
    return JudgeCard(
        CARD_SIGNAL,
        "Signal",
        f"{score_s} · {strength_s}",
        tuple(lines),
        tone="neutral",
    )


def _tone_from_action_gate(action: str, gate: str) -> str:
    a = (action or "").strip().upper()
    g = (gate or "").strip().upper()
    if a in AVOID_LIKE or g in {ACTION_BLOCK, "BLOCKED", "FAIL", "CLOSED"}:
        return "block"
    if a in ENTER_LIKE or g in {"OPEN", "PASS", "CLEAR"}:
        return "open"
    if a in WATCH_LIKE:
        return "watch"
    return "neutral"


def _strip_markup(s: str) -> str:
    """Remove simple Textual/Rich style tags for plain widget paint."""
    return re.sub(r"\[/?[^\]]*\]", "", s or "")


def action_css_class(action: str) -> str:
    a = (action or "").strip().upper()
    if a in ENTER_LIKE or a.startswith(ACTION_ENTER):
        return "action-enter"
    # BLOCKED / BLOCKED(struct) / AVOID — coral like Gate block
    if a in AVOID_LIKE or a.startswith(ACTION_BLOCK) or a.startswith(ACTION_AVOID):
        return "action-avoid"
    if a in WATCH_LIKE or a.startswith(ACTION_WATCH):
        return "action-watch"
    return "action-other"


def gate_css_class(gate: str) -> str:
    g = (gate or "").strip().upper()
    if g in {"OPEN", "PASS", "CLEAR"}:
        return "gate-open"
    if g in {ACTION_BLOCK, "BLOCKED", "FAIL", "CLOSED"}:
        return "gate-block"
    return "gate-other"
