"""Build ADR-063 session packs with exact reference compatibility."""

from __future__ import annotations

import json

from src.application.dto.accumulation_agent import AgentAccumulationContext
from src.application.dto.agent_session import (
    AgentReferenceCompatibility,
    AgentSessionPack,
    AgentSessionPolicy,
    AgentSessionState,
    AgentSessionToolRecord,
)
from src.application.dto.agent_tools import canonical_json_bytes


def classify_context_reference(
    record_context_reference: str,
    *,
    current_context_reference: str,
    record_ticker: str | None,
    current_ticker: str,
    record_schema_id: str | None,
    current_schema_id: str,
) -> AgentReferenceCompatibility:
    if record_ticker and record_ticker.upper() != current_ticker.upper():
        return AgentReferenceCompatibility.INCOMPATIBLE
    if record_schema_id and record_schema_id != current_schema_id:
        return AgentReferenceCompatibility.INCOMPATIBLE
    if record_context_reference == current_context_reference:
        return AgentReferenceCompatibility.FRESH
    return AgentReferenceCompatibility.STALE


def classify_tool_record(
    record: AgentSessionToolRecord,
    *,
    current: AgentAccumulationContext,
) -> AgentReferenceCompatibility:
    # Tool memory is fresh only when captured under the exact current Judge context.
    if record.context_reference == current.context_reference:
        return AgentReferenceCompatibility.FRESH
    if _looks_like_ticker(record.subject) and record.subject != current.ticker:
        return AgentReferenceCompatibility.INCOMPATIBLE
    return AgentReferenceCompatibility.STALE


def build_session_pack(
    state: AgentSessionState,
    *,
    current: AgentAccumulationContext,
    policy: AgentSessionPolicy,
) -> AgentSessionPack:
    fresh: list[AgentSessionToolRecord] = []
    stale: list[AgentSessionToolRecord] = []
    for record in state.tool_records:
        compatibility = classify_tool_record(record, current=current)
        tagged = AgentSessionToolRecord(
            name=record.name,
            status=record.status,
            result_reference=record.result_reference,
            source_reference=record.source_reference,
            as_of=record.as_of,
            schema_id=record.schema_id,
            subject=record.subject,
            context_reference=record.context_reference,
            compatibility=compatibility,
        )
        if compatibility is AgentReferenceCompatibility.FRESH:
            fresh.append(tagged)
        else:
            stale.append(tagged)

    pack_warnings: list[str] = []
    if stale:
        pack_warnings.append(
            "Prior tool results are not current facts for this focus "
            f"({len(stale)} stale/incompatible)"
        )
    anchor = state.anchor_context_reference
    if anchor and anchor != current.context_reference:
        pack_warnings.append(
            "Focused Judge context changed since the previous turn; "
            "treat prior commentary as historical only"
        )

    pack = AgentSessionPack(
        schema_id="agent_session.pack.v1",
        session_id=state.session_id,
        next_turn_sequence=state.turn_count + 1,
        current_context_reference=current.context_reference,
        current_ticker=current.ticker,
        prior_commentary=state.commentary_turns,
        older_commentary_summary=state.older_commentary_summary,
        fresh_tool_records=tuple(fresh),
        stale_or_incompatible_tool_records=tuple(stale),
        structural_warnings=state.structural_warnings,
        structural_failures=state.structural_failures,
        pack_warnings=tuple(pack_warnings),
    )
    size = len(canonical_json_bytes(pack))
    if size <= policy.max_packed_bytes:
        return pack

    # Drop oldest non-authoritative history first (P3/P4/P2), never P0/P1 (current context).
    reduced = pack
    while len(canonical_json_bytes(reduced)) > policy.max_packed_bytes:
        if reduced.stale_or_incompatible_tool_records:
            reduced = AgentSessionPack(
                schema_id=reduced.schema_id,
                session_id=reduced.session_id,
                next_turn_sequence=reduced.next_turn_sequence,
                current_context_reference=reduced.current_context_reference,
                current_ticker=reduced.current_ticker,
                prior_commentary=reduced.prior_commentary,
                older_commentary_summary=reduced.older_commentary_summary,
                fresh_tool_records=reduced.fresh_tool_records,
                stale_or_incompatible_tool_records=reduced.stale_or_incompatible_tool_records[1:],
                structural_warnings=reduced.structural_warnings,
                structural_failures=reduced.structural_failures,
                pack_warnings=reduced.pack_warnings
                + ("Session pack dropped oldest stale tool memory under budget",),
            )
            continue
        if reduced.fresh_tool_records:
            reduced = AgentSessionPack(
                schema_id=reduced.schema_id,
                session_id=reduced.session_id,
                next_turn_sequence=reduced.next_turn_sequence,
                current_context_reference=reduced.current_context_reference,
                current_ticker=reduced.current_ticker,
                prior_commentary=reduced.prior_commentary,
                older_commentary_summary=reduced.older_commentary_summary,
                fresh_tool_records=reduced.fresh_tool_records[1:],
                stale_or_incompatible_tool_records=reduced.stale_or_incompatible_tool_records,
                structural_warnings=reduced.structural_warnings,
                structural_failures=reduced.structural_failures,
                pack_warnings=reduced.pack_warnings
                + ("Session pack dropped oldest fresh tool memory under budget",),
            )
            continue
        if reduced.prior_commentary:
            reduced = AgentSessionPack(
                schema_id=reduced.schema_id,
                session_id=reduced.session_id,
                next_turn_sequence=reduced.next_turn_sequence,
                current_context_reference=reduced.current_context_reference,
                current_ticker=reduced.current_ticker,
                prior_commentary=reduced.prior_commentary[1:],
                older_commentary_summary=reduced.older_commentary_summary,
                fresh_tool_records=reduced.fresh_tool_records,
                stale_or_incompatible_tool_records=reduced.stale_or_incompatible_tool_records,
                structural_warnings=reduced.structural_warnings,
                structural_failures=reduced.structural_failures,
                pack_warnings=reduced.pack_warnings
                + ("Session pack dropped oldest commentary under budget",),
            )
            continue
        if reduced.older_commentary_summary:
            reduced = AgentSessionPack(
                schema_id=reduced.schema_id,
                session_id=reduced.session_id,
                next_turn_sequence=reduced.next_turn_sequence,
                current_context_reference=reduced.current_context_reference,
                current_ticker=reduced.current_ticker,
                prior_commentary=reduced.prior_commentary,
                older_commentary_summary="",
                fresh_tool_records=reduced.fresh_tool_records,
                stale_or_incompatible_tool_records=reduced.stale_or_incompatible_tool_records,
                structural_warnings=reduced.structural_warnings,
                structural_failures=reduced.structural_failures,
                pack_warnings=reduced.pack_warnings
                + ("Session pack cleared older commentary summary under budget",),
            )
            continue
        raise RuntimeError("AGENT_SESSION_CONTEXT_OVERFLOW")
    return reduced


def session_pack_json(pack: AgentSessionPack) -> str:
    from src.application.dto.agent_tools import canonical_json_value

    return json.dumps(
        canonical_json_value(pack),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _looks_like_ticker(value: str | None) -> bool:
    return value is not None and len(value) == 4 and value.isalpha() and value.isupper()
