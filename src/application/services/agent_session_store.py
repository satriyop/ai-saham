"""In-memory single-session store for process-local agent follow-ups."""

from __future__ import annotations

import secrets
from dataclasses import replace

from src.application.dto.agent_session import (
    AgentSessionCommentaryTurn,
    AgentSessionPolicy,
    AgentSessionState,
    AgentSessionToolRecord,
)


def new_session_id() -> str:
    return "sess_" + secrets.token_hex(8)


def new_turn_id() -> str:
    return "turn_" + secrets.token_hex(8)


class InMemoryAgentSessionStore:
    """At most one active session; nothing is written to disk."""

    def __init__(self, policy: AgentSessionPolicy) -> None:
        self._policy = policy
        self._state: AgentSessionState | None = None

    @property
    def policy(self) -> AgentSessionPolicy:
        return self._policy

    def get(self) -> AgentSessionState | None:
        return self._state

    def reset(self) -> AgentSessionState:
        state = AgentSessionState(
            session_id=new_session_id(),
            turn_count=0,
            anchor_context_reference=None,
            anchor_ticker=None,
            anchor_schema_id=None,
            commentary_turns=(),
            older_commentary_summary="",
            tool_records=(),
            structural_warnings=(),
            structural_failures=(),
            in_flight=False,
        )
        self._state = state
        return state

    def ensure(self) -> AgentSessionState:
        if self._state is None:
            return self.reset()
        return self._state

    def begin_turn(self) -> AgentSessionState:
        state = self.ensure()
        if state.in_flight:
            raise RuntimeError("AGENT_SESSION_IN_FLIGHT")
        if state.turn_count >= self._policy.max_turns:
            raise RuntimeError("AGENT_SESSION_MAX_TURNS")
        state = replace(state, in_flight=True)
        self._state = state
        return state

    def abort_turn(self) -> None:
        if self._state is None:
            return
        self._state = replace(self._state, in_flight=False)

    def commit_turn(
        self,
        *,
        commentary: AgentSessionCommentaryTurn | None,
        tool_records: tuple[AgentSessionToolRecord, ...],
        anchor_context_reference: str,
        anchor_ticker: str,
        anchor_schema_id: str,
        structural_warnings: tuple[str, ...] = (),
        structural_failures: tuple[str, ...] = (),
    ) -> AgentSessionState:
        state = self.ensure()
        turns = list(state.commentary_turns)
        summary = state.older_commentary_summary
        if commentary is not None:
            turns.append(commentary)
            while len(turns) > self._policy.max_full_commentary_turns:
                dropped = turns.pop(0)
                summary = _append_summary(summary, dropped, self._policy.max_older_summary_chars)
        tools = list(state.tool_records) + list(tool_records)
        tools = tools[-self._policy.max_fresh_tool_records :]
        state = AgentSessionState(
            session_id=state.session_id,
            turn_count=state.turn_count + 1,
            anchor_context_reference=anchor_context_reference,
            anchor_ticker=anchor_ticker,
            anchor_schema_id=anchor_schema_id,
            commentary_turns=tuple(turns),
            older_commentary_summary=summary,
            tool_records=tuple(tools),
            structural_warnings=tuple(
                dict.fromkeys(state.structural_warnings + structural_warnings)
            ),
            structural_failures=tuple(
                dict.fromkeys(state.structural_failures + structural_failures)
            ),
            in_flight=False,
        )
        self._state = state
        return state


def _append_summary(
    existing: str,
    turn: AgentSessionCommentaryTurn,
    max_chars: int,
) -> str:
    """Deterministic older-commentary compression — commentary only, no authority."""
    piece = (
        f"[turn {turn.turn_sequence} status={turn.status} "
        f"ctx={turn.context_reference}] Q: {turn.question.strip()} "
        f"A: {turn.answer.strip()}"
    )
    if existing:
        combined = f"{existing}\n{piece}"
    else:
        combined = piece
    if len(combined) <= max_chars:
        return combined
    # Keep the newest summary tail; never invent scores/Action.
    return combined[-max_chars:]
