"""Pure, allow-listed projection for plan-swing structure desk (ADR-066)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace

from src.application.dto.accumulation_agent import AgentPlanSwingContext
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
)

SCHEMA_ID = "tui_agent.plan_swing.v1"
_TICKER_PATTERN = re.compile(r"[A-Z]{4}")


@dataclass(frozen=True)
class AgentPlanSwingRawInput:
    """Typed raw input for the plan_swing builder (assembled by the adapter)."""

    ticker: str
    action: str = "—"
    entry: str = "—"
    stop: str = "—"
    target: str = "—"
    lots: str = "—"
    risk_pct: str = "—"
    horizon: str = "swing"
    incomplete_reason: str = ""
    plan_id_short: str = ""
    inherits_action: bool = True
    no_order: bool = True
    summary: str = ""
    board_kind: str | None = None
    board_signal: str | None = None
    board_accum: str | None = None
    board_gate: str | None = None
    board_action: str | None = None
    running: bool = False


def build_agent_plan_swing_context(raw: AgentPlanSwingRawInput) -> AgentPlanSwingContext:
    """Project plan structure facts; refuse while running or without focus ticker."""
    if not isinstance(raw, AgentPlanSwingRawInput):
        raise TypeError(
            f"plan_swing raw input must be AgentPlanSwingRawInput, got {type(raw).__name__}"
        )
    if raw.running:
        raise AgentContextUnavailableError(
            "Plan swing context unavailable: structure still running"
        )
    ticker = str(raw.ticker or "").strip().upper()
    if _TICKER_PATTERN.fullmatch(ticker) is None:
        raise AgentContextUnavailableError(
            f"Plan swing context unavailable: invalid ticker {raw.ticker!r}"
        )

    action = _dash(raw.action)
    entry = _dash(raw.entry)
    stop = _dash(raw.stop)
    target = _dash(raw.target)
    lots = _dash(raw.lots)
    geometry_available = any(v not in {"—", ""} for v in (entry, stop, target, lots))
    incomplete = str(raw.incomplete_reason or "").strip()
    summary = str(raw.summary or "").strip()

    if not geometry_available and not incomplete and not summary:
        raise AgentContextUnavailableError(
            "Plan swing context unavailable: no structure facts for focused ticker"
        )

    board_action = _optional(raw.board_action)
    if (
        board_action is not None
        and action not in {"—", ""}
        and board_action.upper() != action.upper()
        and str(raw.inherits_action).lower() in {"true", "1"}
    ):
        # Soft identity: structure may still be incomplete; only hard-fail when both
        # claim a concrete Action and disagree.
        if board_action not in {"—", "-"} and action not in {"—", "-"}:
            raise AgentContextInvariantError(
                f"Plan swing Action mismatch: board={board_action} structure={action}"
            )

    warnings: list[str] = []
    if not geometry_available:
        warnings.append("Plan geometry incomplete · structure-only · no order")
    if incomplete:
        warnings.append(incomplete)
    if not raw.no_order:
        # Defensive: product contract is always no-order on this desk.
        warnings.append("Plan desk must remain no-order (forced non-authoritative)")

    context = AgentPlanSwingContext(
        schema_id=SCHEMA_ID,
        context_reference="",
        ticker=ticker,
        action=action,
        entry=entry,
        stop=stop,
        target=target,
        lots=lots,
        risk_pct=_dash(raw.risk_pct),
        horizon=str(raw.horizon or "swing").strip() or "swing",
        incomplete_reason=incomplete,
        plan_id_short=str(raw.plan_id_short or "").strip(),
        inherits_action=bool(raw.inherits_action),
        no_order=True,  # hard lock: cockpit never places orders
        geometry_available=geometry_available,
        summary=summary,
        board_kind=_optional(raw.board_kind),
        board_signal=_optional(raw.board_signal),
        board_accum=_optional(raw.board_accum),
        board_gate=_optional(raw.board_gate),
        board_action=board_action,
        warnings=tuple(dict.fromkeys(warnings)),
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


def _dash(value: object) -> str:
    s = str(value or "").strip()
    if not s or s in {"None", "-"}:
        return "—"
    return s


def _optional(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in {"—", "-", "None"}:
        return None
    return s
