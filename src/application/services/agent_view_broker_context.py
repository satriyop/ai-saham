"""Pure, allow-listed projection for view-broker desk stage (ADR-066)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace

from src.application.dto.accumulation_agent import AgentViewBrokerContext
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
)
from src.application.services.agent_broker_desk_tool import (
    BrokerDeskResultData,
    project_broker_desk_from_result,
)

SCHEMA_ID = "tui_agent.view_broker.v1"
_BROKER_CODE_PATTERN = re.compile(r"[A-Z]{2}")
_PAGE_TO_VIEW = {
    "show": "SHOW",
    "top": "TOP_STOCKS",
    "matrix": "TOP_MATRIX",
    "flow": "FLOW",
    "cal": "CALENDAR",
    "history": "HISTORY",
}


def tui_page_to_desk_view(page: str) -> str:
    """Map TUI broker_page keys to closed tool view enum."""
    key = (page or "").strip().lower()
    if key not in _PAGE_TO_VIEW:
        raise AgentContextUnavailableError(
            f"View broker context unavailable: unsupported desk page {page!r}"
        )
    return _PAGE_TO_VIEW[key]


def build_agent_view_broker_context_from_result(
    page: str,
    result: object | None,
) -> AgentViewBrokerContext:
    """Project a use-case desk result for the given TUI page into stage context."""
    view = tui_page_to_desk_view(page)
    projected = project_broker_desk_from_result(view, result)
    if projected is None:
        raise AgentContextUnavailableError(
            f"View broker context unavailable: no cached desk data for view {view}"
        )
    data, warnings, _as_of = projected
    return build_agent_view_broker_context(data, warnings=warnings)


def build_agent_view_broker_context(
    data: BrokerDeskResultData,
    *,
    warnings: tuple[str, ...] = (),
) -> AgentViewBrokerContext:
    """Wrap an allow-listed desk projection with identity + content hash."""
    if not isinstance(data, BrokerDeskResultData):
        raise TypeError(
            f"view_broker raw input must be BrokerDeskResultData, got {type(data).__name__}"
        )
    code = str(data.broker_code or "").strip().upper()
    if _BROKER_CODE_PATTERN.fullmatch(code) is None:
        raise AgentContextUnavailableError(
            f"View broker context unavailable: invalid broker code {data.broker_code!r}"
        )
    view = str(data.view or "").strip().upper()
    if view not in _PAGE_TO_VIEW.values():
        raise AgentContextUnavailableError(
            f"View broker context unavailable: unsupported view {data.view!r}"
        )
    if str(data.broker_code).upper() != code:
        raise AgentContextInvariantError(
            f"View broker code mismatch: {data.broker_code!r} vs {code!r}"
        )

    context = AgentViewBrokerContext(
        schema_id=SCHEMA_ID,
        context_reference="",
        broker_code=code,
        broker_name=str(data.broker_name or ""),
        broker_type=str(data.broker_type or ""),
        view=view,
        as_of=data.as_of,
        scope_note=str(data.scope_note or ""),
        show=data.show,
        top_stocks=data.top_stocks,
        top_matrix=data.top_matrix,
        flow=data.flow,
        calendar=data.calendar,
        history=data.history,
        warnings=warnings,
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
