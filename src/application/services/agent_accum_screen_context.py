"""Pure, allow-listed cohort projection for accumulation screen board (ADR-066)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from src.application.dto.accumulation_agent import (
    AgentAccumScreenCandidateSummary,
    AgentAccumScreenContext,
)
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.dto.agent_tools import canonical_reference
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
)

SCHEMA_ID = "tui_agent.accum_screen.v1"
SCREEN_KIND = "accum"
# ADR-066 D3: fixed cohort bound (amendment required to raise).
COHORT_TOP_N = 20


@dataclass(frozen=True)
class AgentAccumScreenRawInput:
    """Typed raw input for the accum_screen builder (assembled by the adapter)."""

    candidates: tuple[AccumulationCandidate, ...]
    universe: str
    window_days: int
    sort_by: str = "signal"
    top_limit: int | None = None
    as_of: date | None = None
    regime: str | None = None
    # Allow-listed filter/policy facts (key, value) for cohort identity.
    filter_policy: tuple[tuple[str, str | int | float | bool | None], ...] = ()


def build_agent_accum_screen_context(
    raw: AgentAccumScreenRawInput,
) -> AgentAccumScreenContext:
    """Project a bounded top-N board summary with cohort identity validation."""
    if not isinstance(raw, AgentAccumScreenRawInput):
        raise TypeError(
            f"accum_screen raw input must be AgentAccumScreenRawInput, got {type(raw).__name__}"
        )
    candidates = raw.candidates
    if not candidates:
        raise AgentContextUnavailableError(
            "Accumulation screen context unavailable: empty board (no candidates)"
        )
    universe = (raw.universe or "").strip().lower()
    if not universe:
        raise AgentContextUnavailableError(
            "Accumulation screen context unavailable: universe reference missing"
        )
    if raw.window_days <= 0:
        raise AgentContextUnavailableError(
            "Accumulation screen context unavailable: window_days must be positive"
        )

    cohort_total = len(candidates)
    shown = min(COHORT_TOP_N, cohort_total)
    # Board order is the screen's deterministic rank — never re-sort here.
    ranked = candidates[:shown]

    member_as_ofs: list[date] = []
    members: list[AgentAccumScreenCandidateSummary] = []
    for index, candidate in enumerate(ranked, start=1):
        if not isinstance(candidate, AccumulationCandidate):
            raise TypeError(
                "accum_screen candidates must be AccumulationCandidate, "
                f"got {type(candidate).__name__}"
            )
        as_of = _candidate_as_of(candidate)
        if as_of is None:
            raise AgentContextUnavailableError(
                f"Accumulation screen context unavailable: {candidate.ticker} has no as-of date"
            )
        member_as_ofs.append(as_of)
        members.append(
            AgentAccumScreenCandidateSummary(
                rank=index,
                ticker=str(candidate.ticker).upper(),
                as_of=as_of,
                signal_score=_signal_score(candidate),
                accum_score=_float_or_none(getattr(candidate, "accum_score", None)),
                action=_action(candidate),
                phase=_phase(candidate),
                streak=_int_or_none(getattr(candidate, "consecutive_streak", None)),
                gate=_gate(candidate),
                net_buy_ratio=_float_or_none(getattr(candidate, "net_buy_ratio", None)),
            )
        )

    board_as_of = raw.as_of
    if board_as_of is None:
        # Prefer unanimous member as-of; otherwise refuse to invent a date.
        unique = set(member_as_ofs)
        if len(unique) != 1:
            raise AgentContextInvariantError(
                "Accumulation screen member as-of dates disagree and board as_of is missing: "
                + ", ".join(sorted(d.isoformat() for d in unique))
            )
        board_as_of = next(iter(unique))

    mismatched = [m for m in members if m.as_of != board_as_of]
    if mismatched:
        raise AgentContextInvariantError(
            "Accumulation screen member as-of disagree with cohort as_of "
            f"{board_as_of.isoformat()}: "
            + ", ".join(f"{m.ticker}@{m.as_of.isoformat()}" for m in mismatched[:5])
        )

    if shown != min(COHORT_TOP_N, cohort_total):
        raise AgentContextInvariantError(
            f"shown invariant failed: shown={shown}, "
            f"min({COHORT_TOP_N}, {cohort_total})={min(COHORT_TOP_N, cohort_total)}"
        )

    filter_policy = tuple(raw.filter_policy)
    ranked_tickers = tuple(m.ticker for m in members)
    # canonical_reference accepts dataclasses/tuples/scalars only (no bare dict).
    cohort_identity = canonical_reference(
        (
            ("as_of_date", board_as_of.isoformat()),
            ("screen_kind", SCREEN_KIND),
            ("filter_policy", filter_policy),
            ("window_days", raw.window_days),
            ("sort_by", raw.sort_by),
            ("top_limit", raw.top_limit),
            ("universe", universe),
            ("ranked_member_tickers", ranked_tickers),
            ("cohort_total", cohort_total),
        )
    )

    context = AgentAccumScreenContext(
        schema_id=SCHEMA_ID,
        context_reference="",
        as_of=board_as_of,
        screen_kind=SCREEN_KIND,
        universe=universe,
        window_days=raw.window_days,
        sort_by=raw.sort_by,
        top_limit=raw.top_limit,
        regime=raw.regime,
        filter_policy=filter_policy,
        cohort_total=cohort_total,
        shown=shown,
        members=tuple(members),
        cohort_identity=cohort_identity,
        warnings=(),
    )
    canonical = json.dumps(
        context.canonical_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return replace(
        context,
        context_reference="sha256:" + hashlib.sha256(canonical).hexdigest(),
    )


def _candidate_as_of(candidate: AccumulationCandidate) -> date | None:
    trade = getattr(candidate, "trade_setup", None)
    if trade is not None:
        snap = getattr(trade, "snapshot_date", None)
        if isinstance(snap, date):
            return snap
    for attr in ("latest_candle_date", "latest_broker_date"):
        value = getattr(candidate, attr, None)
        if isinstance(value, date):
            return value
    response = getattr(candidate, "signal_assessment", None)
    assessment = getattr(response, "assessment", None) if response is not None else None
    snap = getattr(assessment, "snapshot_date", None)
    if isinstance(snap, date):
        return snap
    return None


def _signal_score(candidate: AccumulationCandidate) -> int | None:
    response = getattr(candidate, "signal_assessment", None)
    assessment = getattr(response, "assessment", None) if response is not None else None
    if assessment is not None:
        score = getattr(assessment, "score", None)
        if score is not None:
            return int(score)
    trade = getattr(candidate, "trade_setup", None)
    if trade is not None:
        score = getattr(trade, "signal_score", None)
        if score is not None:
            return int(score)
    return None


def _action(candidate: AccumulationCandidate) -> str | None:
    trade = getattr(candidate, "trade_setup", None)
    if trade is None:
        return None
    action = getattr(trade, "action", None)
    if action is None:
        return None
    return str(getattr(action, "value", action))


def _phase(candidate: AccumulationCandidate) -> str | None:
    phase = getattr(candidate, "setup_phase", None)
    if phase is None:
        return None
    current = getattr(phase, "current_phase", None) or getattr(phase, "phase", None)
    if current is None:
        return None
    return str(getattr(current, "value", current))


def _gate(candidate: AccumulationCandidate) -> str | None:
    trade = getattr(candidate, "trade_setup", None)
    if trade is None:
        return None
    gates = getattr(trade, "blocking_gates", None) or ()
    if not gates:
        return None
    return ",".join(str(g) for g in gates)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
