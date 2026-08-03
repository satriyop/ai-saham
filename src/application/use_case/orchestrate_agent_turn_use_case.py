"""Deterministic one-turn orchestration for closed read-only agent tools."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Callable, TypeVar

from src.application.dto.accumulation_agent import (
    AgentModelRequest,
    AgentModelResponse,
    AgentModelResponseKind,
    AgentTurnRequest,
    AgentTurnResult,
    AgentTurnStatus,
)
from src.application.dto.agent_session import AgentSessionPack
from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentModelToolChoice,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolProvenance,
    AgentToolTurnPolicy,
)
from src.application.ports.agent_model import (
    AgentModelAuthenticationError,
    AgentModelMalformedResponseError,
    AgentModelPort,
    AgentModelRateLimitError,
    AgentModelTimeoutError,
    AgentModelTransportError,
    AgentModelUnavailableError,
)
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
    build_agent_accumulation_context,
)
from src.application.services.agent_tool_registry import (
    AgentToolExecutionContractError,
    AgentToolRegistry,
    AgentToolValidationError,
    PreparedAgentToolCall,
)
from src.application.use_case.explain_accumulation_candidate_use_case import SYSTEM_POLICY

_T = TypeVar("_T")
TimedCallRunner = Callable[[Callable[[], _T], float], _T]


class AgentTurnOrchestrator:
    def __init__(
        self,
        model: AgentModelPort,
        registry: AgentToolRegistry,
        policy: AgentToolTurnPolicy,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        timed_call: TimedCallRunner = None,
    ) -> None:
        self._model = model
        self._registry = registry
        self._policy = policy
        self._monotonic = monotonic
        self._timed_call = timed_call or _run_with_timeout

    def execute(
        self,
        request: AgentTurnRequest,
        *,
        is_cancelled: Callable[[], bool] | None = None,
        session_pack: AgentSessionPack | None = None,
    ) -> AgentTurnResult:
        cancelled = is_cancelled or (lambda: False)
        text = request.user_text.strip()
        if not text:
            return _failed("Question cannot be empty")
        if len(text) > 2_000:
            return _failed("Question exceeds 2000 character limit")
        try:
            context = build_agent_accumulation_context(request.candidate)
        except AgentContextUnavailableError as exc:
            return AgentTurnResult(status=AgentTurnStatus.UNAVAILABLE, error_message=str(exc))
        except AgentContextInvariantError as exc:
            return _failed(f"Canonical Judge context failed identity validation: {exc}")
        if cancelled():
            return _cancelled()

        started = self._monotonic()
        tool_context = AgentToolExecutionContext(visible_accumulation_context=context)
        definitions = (
            self._registry.definitions
            if self._policy.tools_enabled and not self._registry.empty
            else ()
        )
        initial_request = AgentModelRequest(
            system_policy=SYSTEM_POLICY,
            user_text=text,
            context=context,
            max_output_tokens=500,
            tool_definitions=definitions,
            tool_choice=(AgentModelToolChoice.AUTO if definitions else AgentModelToolChoice.NONE),
            session_pack=session_pack,
        )
        initial = self._provider_call(initial_request, started)
        if isinstance(initial, AgentTurnResult):
            return initial
        if initial.kind is AgentModelResponseKind.ANSWER:
            return _answer_result(initial, context.context_reference, context.warnings, ())
        if not definitions:
            return _failed("Agent provider proposed tools while tools are disabled")

        try:
            prepared = self._registry.prepare_batch(
                initial.tool_calls,
                max_calls=self._policy.max_tool_calls,
            )
        except AgentToolValidationError:
            return _failed("Agent provider proposed an invalid tool batch")

        tool_started = self._monotonic()
        results: list[AgentToolExecutionResult] = []
        total_bytes = 0
        for call in prepared:
            if cancelled():
                return _cancelled()
            result = self._execute_tool(call, tool_context, started, tool_started)
            if isinstance(result, AgentTurnResult):
                return result
            size = result.serialized_size()
            if size > call.tool.definition.max_result_bytes:
                return _failed("Agent tool result exceeded its size limit")
            total_bytes += size
            if total_bytes > self._policy.max_total_result_bytes:
                return _failed("Agent tool results exceeded the turn size limit")
            results.append(result)

        if cancelled():
            return _cancelled()
        final_request = AgentModelRequest(
            system_policy=SYSTEM_POLICY,
            user_text=text,
            context=context,
            max_output_tokens=500,
            tool_definitions=definitions,
            tool_choice=AgentModelToolChoice.NONE,
            prior_tool_calls=initial.tool_calls,
            tool_results=tuple(results),
            session_pack=session_pack,
        )
        final = self._provider_call(final_request, started)
        if isinstance(final, AgentTurnResult):
            return final
        if final.kind is not AgentModelResponseKind.ANSWER:
            return _failed("Agent provider proposed tools after the final call")
        warnings = context.warnings + tuple(
            warning for result in results for warning in result.warnings
        )
        return _answer_result(final, context.context_reference, warnings, tuple(results))

    def _provider_call(
        self,
        request: AgentModelRequest,
        started: float,
    ) -> AgentModelResponse | AgentTurnResult:
        remaining = self._remaining_turn_seconds(started)
        if remaining <= 0:
            return _failed("Agent turn deadline exceeded")
        timeout = min(self._policy.provider_timeout_seconds, remaining)
        try:
            return self._timed_call(lambda: self._model.generate(request), timeout)
        except (FutureTimeoutError, TimeoutError, AgentModelTimeoutError):
            return _failed("Agent provider timed out")
        except AgentModelAuthenticationError:
            return _failed("Agent provider authentication failed")
        except AgentModelRateLimitError:
            return _failed("Agent provider rate limit reached")
        except AgentModelUnavailableError:
            return _failed("Agent provider is temporarily unavailable")
        except AgentModelMalformedResponseError:
            return _failed("Agent provider returned an invalid response")
        except AgentModelTransportError:
            return _failed("Agent provider transport failed")
        except Exception:
            return _failed("Agent provider failed unexpectedly")

    def _execute_tool(
        self,
        call: PreparedAgentToolCall,
        context: AgentToolExecutionContext,
        turn_started: float,
        tool_started: float,
    ) -> AgentToolExecutionResult | AgentTurnResult:
        turn_remaining = self._remaining_turn_seconds(turn_started)
        tool_remaining = self._policy.tool_budget_seconds - (self._monotonic() - tool_started)
        timeout = min(
            call.tool.definition.timeout_ms / 1_000,
            turn_remaining,
            tool_remaining,
        )
        if timeout <= 0:
            return _failed("Agent tool execution budget exceeded")
        try:
            return self._timed_call(
                lambda: self._registry.execute(call, context),
                timeout,
            )
        except (FutureTimeoutError, TimeoutError):
            return AgentToolExecutionResult.create(
                call_id=call.call_id,
                name=call.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TOOL_TIMEOUT",
                error_message="Agent read tool timed out",
                provenance=AgentToolProvenance(source=call.name.value),
            )
        except AgentToolExecutionContractError:
            return AgentToolExecutionResult.create(
                call_id=call.call_id,
                name=call.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TOOL_CONTRACT",
                error_message="Agent read tool violated its result contract",
                provenance=AgentToolProvenance(source=call.name.value),
            )
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call.call_id,
                name=call.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TOOL_FAILED",
                error_message="Agent read tool failed",
                provenance=AgentToolProvenance(source=call.name.value),
            )

    def _remaining_turn_seconds(self, started: float) -> float:
        return self._policy.turn_deadline_seconds - (self._monotonic() - started)


def _run_with_timeout(call: Callable[[], _T], timeout: float) -> _T:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-read")
    future = executor.submit(call)
    try:
        return future.result(timeout=timeout)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _answer_result(
    response: AgentModelResponse,
    context_reference: str,
    warnings: tuple[str, ...],
    tool_results: tuple[AgentToolExecutionResult, ...],
) -> AgentTurnResult:
    status = (
        AgentTurnStatus.PARTIAL
        if any(result.status is not AgentToolExecutionStatus.SUCCESS for result in tool_results)
        else AgentTurnStatus.SUCCESS
    )
    if response.finish_reason == "length":
        warnings += ("Model answer reached the output limit",)
    return AgentTurnResult(
        status=status,
        answer=response.text,
        context_reference=context_reference,
        provider=response.provider,
        model=response.model,
        response_id=response.response_id,
        warnings=tuple(dict.fromkeys(warnings)),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        tool_results=tool_results,
    )


def _failed(message: str) -> AgentTurnResult:
    return AgentTurnResult(status=AgentTurnStatus.FAILED, error_message=message)


def _cancelled() -> AgentTurnResult:
    return AgentTurnResult(status=AgentTurnStatus.CANCELLED, error_message="Agent turn cancelled")
