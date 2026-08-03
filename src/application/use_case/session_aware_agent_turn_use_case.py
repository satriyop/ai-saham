"""Session-aware wrapper over one-turn agent use cases (ADR-063)."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Protocol

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
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
    build_agent_accumulation_context,
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
    ) -> AgentTurnResult:
        if not self._policy.enabled or not self._session_certified():
            return self._call_inner(request, is_cancelled=is_cancelled, session_pack=None)

        try:
            context = build_agent_accumulation_context(request.candidate)
        except AgentContextUnavailableError as exc:
            return AgentTurnResult(status=AgentTurnStatus.UNAVAILABLE, error_message=str(exc))
        except AgentContextInvariantError as exc:
            return AgentTurnResult(
                status=AgentTurnStatus.FAILED,
                error_message=f"Canonical Judge context failed identity validation: {exc}",
            )

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

        result = self._call_inner(request, is_cancelled=is_cancelled, session_pack=pack)
        if result.status is AgentTurnStatus.CANCELLED:
            self._store.abort_turn()
            return replace(
                result,
                session_id=state.session_id,
                turn_sequence=state.turn_count + 1,
            )

        commentary = None
        tools: tuple[AgentSessionToolRecord, ...] = ()
        failures: tuple[str, ...] = ()
        warnings = pack.pack_warnings
        if result.status in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}:
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
        else:
            failures = (result.error_message or result.status.value,)

        committed = self._store.commit_turn(
            commentary=commentary,
            tool_records=tools,
            anchor_context_reference=context.context_reference,
            anchor_ticker=context.ticker,
            anchor_schema_id=context.schema_id,
            structural_warnings=warnings,
            structural_failures=failures,
        )
        merged_warnings = tuple(dict.fromkeys(result.warnings + pack.pack_warnings))
        return replace(
            result,
            warnings=merged_warnings,
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
    ) -> AgentTurnResult:
        try:
            return self._inner.execute(
                request,
                is_cancelled=is_cancelled,
                session_pack=session_pack,
            )
        except TypeError:
            # Phase 1 use case historically only accepted the request positional.
            if is_cancelled is None and session_pack is None:
                return self._inner.execute(request)  # type: ignore[call-arg]
            return self._inner.execute(  # type: ignore[call-arg]
                request,
                is_cancelled=is_cancelled,
                session_pack=session_pack,
            )


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
