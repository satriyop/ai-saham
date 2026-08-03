"""Pure, allow-listed cohort projection for pre-open screen board (ADR-066)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any

from src.application.dto.accumulation_agent import (
    AgentPreOpenCandidateSummary,
    AgentPreOpenScreenContext,
)
from src.application.dto.agent_tools import canonical_reference
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
)

SCHEMA_ID = "tui_agent.preopen_screen.v1"
SCREEN_KIND = "preopen"
# ADR-066 D3: fixed cohort bound (amendment required to raise).
COHORT_TOP_N = 20


@dataclass(frozen=True)
class AgentPreOpenScreenRawInput:
    """Typed raw input for the preopen_screen builder (assembled by the adapter)."""

    candidates: tuple[Any, ...]  # board-order duck-typed pre-open candidates
    as_of: date
    capture_phase: str | None = None
    ncp_authoritative: bool | None = None
    source_is_live: bool | None = None
    session_source: str | None = None
    session_phase: str | None = None
    regime: str | None = None
    total_movers_seen: int | None = None
    filter_policy: tuple[tuple[str, str | int | float | bool | None], ...] = ()
    # Optional per-ticker display hints already computed by the presenter (ncp/action/risk).
    row_hints: tuple[tuple[str, str | None, str | None, str | None], ...] = ()
    # (ticker, action, ncp, risk)


def build_agent_preopen_screen_context(
    raw: AgentPreOpenScreenRawInput,
) -> AgentPreOpenScreenContext:
    """Project a bounded top-N pre-open board summary with cohort identity validation."""
    if not isinstance(raw, AgentPreOpenScreenRawInput):
        raise TypeError(
            f"preopen_screen raw input must be AgentPreOpenScreenRawInput, got {type(raw).__name__}"
        )
    if not isinstance(raw.as_of, date):
        raise AgentContextUnavailableError(
            "Pre-open screen context unavailable: as_of date missing"
        )
    candidates = raw.candidates
    if not candidates:
        raise AgentContextUnavailableError(
            "Pre-open screen context unavailable: empty board (no candidates)"
        )

    cohort_total = len(candidates)
    shown = min(COHORT_TOP_N, cohort_total)
    ranked = candidates[:shown]
    hints = {
        str(ticker).upper(): (action, ncp, risk) for ticker, action, ncp, risk in raw.row_hints
    }

    members: list[AgentPreOpenCandidateSummary] = []
    for index, candidate in enumerate(ranked, start=1):
        ticker = str(getattr(candidate, "ticker", "") or "").strip().upper()
        if len(ticker) != 4 or not ticker.isalpha():
            raise AgentContextUnavailableError(
                f"Pre-open screen context unavailable: invalid ticker on row {index}"
            )
        member_as_of = _candidate_as_of(candidate) or raw.as_of
        if member_as_of != raw.as_of:
            raise AgentContextInvariantError(
                "Pre-open screen member as-of disagree with cohort as_of "
                f"{raw.as_of.isoformat()}: {ticker}@{member_as_of.isoformat()}"
            )
        action_h, ncp_h, risk_h = hints.get(ticker, (None, None, None))
        members.append(
            AgentPreOpenCandidateSummary(
                rank=index,
                ticker=ticker,
                as_of=raw.as_of,
                action=_str_or_none(action_h) or _action(candidate),
                iep=_num_or_none(getattr(candidate, "iep", None)),
                iep_gap_pct=_gap_pct(candidate),
                iev=_num_or_none(getattr(candidate, "iev", None)),
                ncp=_str_or_none(ncp_h) or _ncp(candidate),
                delta_iev=_delta_iev(candidate),
                risk=_str_or_none(risk_h),
            )
        )

    if shown != min(COHORT_TOP_N, cohort_total):
        raise AgentContextInvariantError(
            f"shown invariant failed: shown={shown}, "
            f"min({COHORT_TOP_N}, {cohort_total})={min(COHORT_TOP_N, cohort_total)}"
        )

    ranked_tickers = tuple(m.ticker for m in members)
    filter_policy = tuple(raw.filter_policy)
    cohort_identity = canonical_reference(
        (
            ("as_of_date", raw.as_of.isoformat()),
            ("screen_kind", SCREEN_KIND),
            ("capture_phase", raw.capture_phase),
            ("ncp_authoritative", raw.ncp_authoritative),
            ("source_is_live", raw.source_is_live),
            ("filter_policy", filter_policy),
            ("ranked_member_tickers", ranked_tickers),
            ("cohort_total", cohort_total),
        )
    )

    context = AgentPreOpenScreenContext(
        schema_id=SCHEMA_ID,
        context_reference="",
        as_of=raw.as_of,
        screen_kind=SCREEN_KIND,
        capture_phase=raw.capture_phase,
        ncp_authoritative=raw.ncp_authoritative,
        source_is_live=raw.source_is_live,
        session_source=raw.session_source,
        session_phase=raw.session_phase,
        regime=raw.regime,
        total_movers_seen=raw.total_movers_seen,
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


def _candidate_as_of(candidate: Any) -> date | None:
    for attr in ("snapshot_date", "as_of", "screened_date"):
        value = getattr(candidate, attr, None)
        if isinstance(value, date):
            return value
    return None


def _action(candidate: Any) -> str | None:
    raw = getattr(candidate, "action", None) or getattr(candidate, "setup_action", None)
    if raw is None:
        return None
    return str(getattr(raw, "value", raw) or "").strip() or None


def _ncp(candidate: Any) -> str | None:
    for key in ("ncp_lock", "ncp_flag", "ncp_phase"):
        raw = getattr(candidate, key, None)
        if raw is not None and str(raw).strip() not in {"", "None"}:
            return str(raw).strip()
    locked = getattr(candidate, "is_ncp_locked", None)
    if locked is True:
        return "LOCK"
    if locked is False:
        return "disc"
    return None


def _gap_pct(candidate: Any) -> float | None:
    gap = getattr(candidate, "iep_gap_pct", None)
    if gap is None:
        gap = getattr(candidate, "gap_pct", None)
    return _num_or_none(gap)


def _delta_iev(candidate: Any) -> float | None:
    raw = getattr(candidate, "delta_iev", None)
    if raw is None:
        raw = getattr(candidate, "locked_delta_iev", None)
    return _num_or_none(raw)


def _num_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in {"—", "-", "None"}:
        return None
    return s
