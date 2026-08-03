"""Session-aware wrapper over one-turn agent use cases (ADR-063)."""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, Callable, Protocol

from src.application.dto.accumulation_agent import (
    AgentTurnRequest,
    AgentTurnResult,
    AgentTurnStatus,
)
from src.application.dto.agent_session import (
    AgentCapabilityCertification,
    AgentSessionCommentaryTurn,
    AgentSessionPack,
    AgentSessionPolicy,
    AgentSessionToolRecord,
)
from src.application.services.agent_session_pack import build_session_pack
from src.application.services.agent_session_store import (
    InMemoryAgentSessionStore,
    new_turn_id,
)

DEEPSEEK_SESSION_CERTIFICATION = AgentCapabilityCertification(
    provider="deepseek",
    model_id="deepseek-v4-flash",
    system_prompt_version="accum_judge_explain.v1",
    tool_schema_version="agent_tools.adr061.v1",
    evaluation_suite_version="agent_suite.v1",
    certified_on=__import__("datetime").date(2026, 8, 2),
    passed=True,
)


class _OneTurnAgent(Protocol):
    def execute(
        self,
        request: AgentTurnRequest,
        *,
        is_cancelled: Callable[[], bool] | None = None,
        session_pack: AgentSessionPack | None = None,
    ) -> AgentTurnResult: ...


class SessionAwareAgentTurnUseCase:
    """Retain process-local follow-up state without durable writes."""

    def __init__(
        self,
        inner: _OneTurnAgent,
        store: InMemoryAgentSessionStore,
        policy: AgentSessionPolicy,
        *,
        certification: AgentCapabilityCertification | None,
        configured_provider: str,
    ) -> None:
        self._inner = inner
        self._store = store
        self._policy = policy
        self._certification = certification
        self._configured_provider = configured_provider.strip().lower()

    @property
    def provider_available(self) -> bool:
        return bool(getattr(self._inner, "provider_available", True))

    @property
    def configured_provider(self) -> str:
        return getattr(self._inner, "configured_provider", self._configured_provider)

    @property
    def session_enabled(self) -> bool:
        return self._policy.enabled

    def reset_session(self) -> str:
        return self._store.reset().session_id

    def execute(
        self,
        request: AgentTurnRequest,
        *,
        is_cancelled: Callable[[], bool] | None = None,
        on_progress: Callable[[str], None] | None = None,
        on_approval: Callable | None = None,
    ) -> AgentTurnResult:
        if not self._policy.enabled or not self._session_certified():
            return self._call_inner(
                request,
                is_cancelled=is_cancelled,
                session_pack=None,
                on_progress=on_progress,
                on_approval=on_approval,
            )

        # ADR-066 D1: built once at open; session layer consumes the passed projection.
        context = request.stage_context

        try:
            state = self._store.begin_turn()
        except RuntimeError as exc:
            code = str(exc)
            if code == "AGENT_SESSION_IN_FLIGHT":
                return _failed("Agent session already has an in-flight turn")
            if code == "AGENT_SESSION_MAX_TURNS":
                return _failed("Agent session reached the maximum of 8 turns; reset the session")
            return _failed("Agent session could not begin a turn")

        try:
            pack = build_session_pack(state, current=context, policy=self._policy)
        except RuntimeError as exc:
            self._store.abort_turn()
            if str(exc) == "AGENT_SESSION_CONTEXT_OVERFLOW":
                return _failed("Agent session context budget exceeded; reset the session")
            return _failed("Agent session pack failed")

        result = self._call_inner(
            request,
            is_cancelled=is_cancelled,
            session_pack=pack,
            on_progress=on_progress,
            on_approval=on_approval,
        )
        # ADR-064 fail-safe: only SUCCESS/PARTIAL commit commentary/tool memory.
        # FAIL/CANCEL/UNAVAILABLE leave session as before this Enter.
        if result.status not in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}:
            self._store.abort_turn()
            return replace(
                result,
                session_id=state.session_id,
                turn_sequence=state.turn_count + 1,
            )

        commentary = AgentSessionCommentaryTurn(
            turn_sequence=state.turn_count + 1,
            turn_id=new_turn_id(),
            question=request.user_text.strip(),
            answer=result.answer,
            status=result.status.value,
            context_reference=result.context_reference or context.context_reference,
            warnings=result.warnings,
        )
        tools = tuple(
            AgentSessionToolRecord(
                name=item.name.value,
                status=item.status.value,
                result_reference=item.result_reference,
                source_reference=item.source_reference,
                as_of=item.provenance.as_of,
                schema_id=getattr(item.data, "schema_id", None) if item.data else None,
                subject=_tool_subject(item),
                context_reference=context.context_reference,
            )
            for item in result.tool_results
        )

        merged_warnings = tuple(dict.fromkeys(result.warnings + pack.pack_warnings))
        # Cross-turn display dedupe: hide data notes already shown earlier in-session.
        prior_seen = set(state.structural_warnings)
        display_warnings = tuple(item for item in merged_warnings if item not in prior_seen)
        committed = self._store.commit_turn(
            commentary=commentary,
            tool_records=tools,
            anchor_context_reference=context.context_reference,
            anchor_ticker=context.session_subject,
            anchor_schema_id=context.schema_id,
            structural_warnings=merged_warnings,
            structural_failures=(),
        )
        return replace(
            result,
            warnings=display_warnings,
            session_id=committed.session_id,
            turn_sequence=committed.turn_count,
        )

    def _session_certified(self) -> bool:
        cert = self._certification
        if cert is None or not cert.passed:
            return False
        return cert.provider == self._configured_provider

    def _call_inner(
        self,
        request: AgentTurnRequest,
        *,
        is_cancelled: Callable[[], bool] | None,
        session_pack: AgentSessionPack | None,
        on_progress: Callable[[str], None] | None = None,
        on_approval: Callable | None = None,
    ) -> AgentTurnResult:
        # Detect the inner use case's supported kwargs ONCE, up front, rather
        # than catching a TypeError and retrying with fewer args. Retrying on an
        # execution error would re-run a turn that already started executing —
        # double provider spend / double egress, and re-running without the
        # approval callback (ADR-065 invariant 2). Signature-probe instead so the
        # turn runs exactly once; a genuine execution error propagates.
        kwargs = _supported_kwargs(
            self._inner.execute,
            {
                "is_cancelled": is_cancelled,
                "session_pack": session_pack,
                "on_progress": on_progress,
                "on_approval": on_approval,
            },
        )
        return self._inner.execute(request, **kwargs)  # type: ignore[call-arg]


def _supported_kwargs(func: Callable, candidate: dict[str, Any]) -> dict[str, Any]:
    """Filter ``candidate`` to the keyword params ``func`` actually accepts.

    Used once before invoking the inner use case so the turn runs exactly once
    (no TypeError-catch retry ladder). If the signature cannot be introspected or
    the callable accepts ``**kwargs``, pass everything through unchanged.
    """
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return dict(candidate)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(candidate)
    return {name: value for name, value in candidate.items() if name in params}


def _tool_subject(item) -> str | None:
    data = item.data
    if data is None:
        return None
    for attr in ("ticker", "broker_code"):
        value = getattr(data, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _failed(message: str) -> AgentTurnResult:
    return AgentTurnResult(status=AgentTurnStatus.FAILED, error_message=message)
