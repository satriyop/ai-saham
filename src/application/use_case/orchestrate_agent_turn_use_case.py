"""Deterministic orchestration for closed read-only Research Cockpit tools.

L1 (ADR-061): one tool batch, two tools, two provider calls.
L3 (ADR-064): multi-round OUR tools — 3 rounds / 4 tools / 2 per batch when
``AgentToolTurnPolicy.multi_round`` is true.

Layer: Application
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TypeVar

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
    AgentApprovalRequest,
    AgentModelToolCall,
    AgentModelToolChoice,
    AgentToolApproval,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolGapClue,
    AgentToolProvenance,
    AgentToolSideEffect,
    AgentToolTurnPolicy,
    canonical_json_bytes,
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
ProgressCallback = Callable[[str], None]
ApprovalCallback = Callable[[AgentApprovalRequest], bool]


class AgentTurnOrchestrator:
    def __init__(
        self,
        model: AgentModelPort,
        registry: AgentToolRegistry,
        policy: AgentToolTurnPolicy,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        timed_call: TimedCallRunner = None,
        on_progress: ProgressCallback | None = None,
        on_approval: ApprovalCallback | None = None,
    ) -> None:
        self._model = model
        self._registry = registry
        self._policy = policy
        self._monotonic = monotonic
        self._timed_call = timed_call or _run_with_timeout
        self._on_progress = on_progress
        self._on_approval = on_approval

    def execute(
        self,
        request: AgentTurnRequest,
        *,
        is_cancelled: Callable[[], bool] | None = None,
        session_pack: AgentSessionPack | None = None,
        on_progress: ProgressCallback | None = None,
        on_approval: ApprovalCallback | None = None,
    ) -> AgentTurnResult:
        cancelled = is_cancelled or (lambda: False)
        progress = on_progress or self._on_progress or (lambda _m: None)
        approval = on_approval or self._on_approval
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
        if not definitions:
            # Zero-tool path: single provider call (L1 / tools off).
            return self._single_answer_path(
                text=text,
                context=context,
                session_pack=session_pack,
                started=started,
                cancelled=cancelled,
            )

        if not self._policy.multi_round:
            return self._l1_path(
                text=text,
                context=context,
                tool_context=tool_context,
                definitions=definitions,
                session_pack=session_pack,
                started=started,
                cancelled=cancelled,
                progress=progress,
                approval=approval,
            )

        return self._l3_path(
            text=text,
            context=context,
            tool_context=tool_context,
            definitions=definitions,
            session_pack=session_pack,
            started=started,
            cancelled=cancelled,
            progress=progress,
            approval=approval,
        )

    def _single_answer_path(
        self,
        *,
        text: str,
        context,
        session_pack: AgentSessionPack | None,
        started: float,
        cancelled: Callable[[], bool],
    ) -> AgentTurnResult:
        if cancelled():
            return _cancelled()
        req = AgentModelRequest(
            system_policy=SYSTEM_POLICY,
            user_text=text,
            context=context,
            max_output_tokens=500,
            tool_definitions=(),
            tool_choice=AgentModelToolChoice.NONE,
            session_pack=session_pack,
        )
        response = self._provider_call(req, started)
        if isinstance(response, AgentTurnResult):
            return response
        if response.kind is not AgentModelResponseKind.ANSWER:
            return _failed("Agent provider proposed tools while tools are disabled")
        return _answer_result(response, context.context_reference, context.warnings, ())

    def _l1_path(
        self,
        *,
        text: str,
        context,
        tool_context: AgentToolExecutionContext,
        definitions,
        session_pack: AgentSessionPack | None,
        started: float,
        cancelled: Callable[[], bool],
        progress: ProgressCallback,
        approval: ApprovalCallback | None,
    ) -> AgentTurnResult:
        """Exact ADR-061: auto → optional one batch ≤2 → forced none (+ L4 confirm/gaps)."""
        progress("AI Research Cockpit · round 1/2")
        initial_request = AgentModelRequest(
            system_policy=SYSTEM_POLICY,
            user_text=text,
            context=context,
            max_output_tokens=500,
            tool_definitions=definitions,
            tool_choice=AgentModelToolChoice.AUTO,
            session_pack=session_pack,
        )
        initial = self._provider_call(initial_request, started)
        if isinstance(initial, AgentTurnResult):
            return initial
        if initial.kind is AgentModelResponseKind.ANSWER:
            return _answer_result(
                initial,
                context.context_reference,
                context.warnings,
                (),
                tools_offered=True,
            )

        try:
            batch = self._registry.prepare_batch_result(
                initial.tool_calls,
                max_calls=self._policy.max_tools_per_batch,
                allow_gaps=True,
            )
        except AgentToolValidationError:
            return _failed("Agent provider proposed an invalid tool batch")

        gap_clues = list(batch.gaps)
        tool_started = self._monotonic()
        results, err, elevated = self._run_batch(
            batch.prepared,
            tool_context=tool_context,
            started=started,
            tool_started=tool_started,
            cancelled=cancelled,
            progress=progress,
            approval=approval,
            total_bytes=0,
            seen_identities=set(),
        )
        if err is not None:
            return _with_gaps(err, gap_clues, elevated_attempted=elevated)
        assert results is not None

        if cancelled():
            return _cancelled()
        if not results and gap_clues and not batch.prepared:
            # Only gaps — still force a final answer honesty path
            progress("AI Research Cockpit · round 2/2 · final answer")
            final_only = self._provider_call(
                AgentModelRequest(
                    system_policy=SYSTEM_POLICY,
                    user_text=text,
                    context=context,
                    max_output_tokens=500,
                    tool_definitions=definitions,
                    tool_choice=AgentModelToolChoice.NONE,
                    session_pack=session_pack,
                ),
                started,
            )
            if isinstance(final_only, AgentTurnResult):
                return _with_gaps(final_only, gap_clues)
            if final_only.kind is not AgentModelResponseKind.ANSWER:
                return _with_gaps(
                    _failed("Agent provider proposed tools after the final call"),
                    gap_clues,
                )
            return _answer_result(
                final_only,
                context.context_reference,
                context.warnings + tuple(g.operator_line() for g in gap_clues),
                (),
                tools_offered=True,
                gap_clues=tuple(gap_clues),
            )

        progress("AI Research Cockpit · round 2/2 · final answer")
        # Prior history only for executed tools (denies included as results)
        prior_calls = tuple(
            c for c in initial.tool_calls if any(r.call_id == c.call_id for r in results)
        )
        final_request = AgentModelRequest(
            system_policy=SYSTEM_POLICY,
            user_text=text,
            context=context,
            max_output_tokens=500,
            tool_definitions=definitions,
            tool_choice=AgentModelToolChoice.NONE,
            prior_tool_calls=prior_calls,
            tool_results=tuple(results),
            session_pack=session_pack,
        )
        final = self._provider_call(final_request, started)
        if isinstance(final, AgentTurnResult):
            return _with_gaps(final, gap_clues, elevated_attempted=elevated)
        if final.kind is not AgentModelResponseKind.ANSWER:
            return _with_gaps(
                _failed("Agent provider proposed tools after the final call"),
                gap_clues,
                elevated_attempted=elevated,
                restore=elevated,
            )
        warnings = context.warnings + tuple(
            warning for result in results for warning in result.warnings
        )
        warnings = warnings + tuple(g.operator_line() for g in gap_clues)
        return _answer_result(
            final,
            context.context_reference,
            warnings,
            tuple(results),
            tools_offered=True,
            gap_clues=tuple(gap_clues),
            elevated_attempted=elevated,
        )

    def _l3_path(
        self,
        *,
        text: str,
        context,
        tool_context: AgentToolExecutionContext,
        definitions,
        session_pack: AgentSessionPack | None,
        started: float,
        cancelled: Callable[[], bool],
        progress: ProgressCallback,
        approval: ApprovalCallback | None,
    ) -> AgentTurnResult:
        """ADR-064 multi-round: up to 3 provider rounds and 4 tool executions."""
        max_rounds = self._policy.max_provider_calls
        max_tools = self._policy.max_tool_calls
        rounds_used = 0
        tools_used = 0
        all_calls: list[AgentModelToolCall] = []
        all_results: list[AgentToolExecutionResult] = []
        seen_identities: set[tuple[str, bytes]] = set()
        tool_started = self._monotonic()
        total_bytes = 0
        gap_clues: list[AgentToolGapClue] = []
        elevated_any = False

        while rounds_used < max_rounds:
            if cancelled():
                return _cancelled()
            remaining_tools = max_tools - tools_used
            # Last allowed provider call must use tool_choice=none.
            forced_final = (rounds_used == max_rounds - 1) or (remaining_tools <= 0)
            choice = AgentModelToolChoice.NONE if forced_final else AgentModelToolChoice.AUTO
            round_label = rounds_used + 1
            if forced_final:
                progress(f"AI Research Cockpit · round {round_label}/{max_rounds} · final answer")
            else:
                progress(f"AI Research Cockpit · round {round_label}/{max_rounds}")

            model_request = AgentModelRequest(
                system_policy=SYSTEM_POLICY,
                user_text=text,
                context=context,
                max_output_tokens=500,
                tool_definitions=definitions,
                tool_choice=choice,
                prior_tool_calls=tuple(all_calls),
                tool_results=tuple(all_results),
                session_pack=session_pack,
            )
            response = self._provider_call(model_request, started)
            if isinstance(response, AgentTurnResult):
                return _with_gaps(response, gap_clues, elevated_attempted=elevated_any)
            rounds_used += 1

            if response.kind is AgentModelResponseKind.ANSWER:
                if not response.text.strip():
                    return _with_gaps(
                        _failed("Agent provider returned an empty answer"),
                        gap_clues,
                        elevated_attempted=elevated_any,
                    )
                warnings = context.warnings + tuple(
                    warning for result in all_results for warning in result.warnings
                )
                warnings = warnings + tuple(g.operator_line() for g in gap_clues)
                return _answer_result(
                    response,
                    context.context_reference,
                    warnings,
                    tuple(all_results),
                    tools_offered=True,
                    gap_clues=tuple(gap_clues),
                    elevated_attempted=elevated_any,
                )

            if forced_final:
                return _with_gaps(
                    _failed("Agent provider proposed tools after the final call"),
                    gap_clues,
                    elevated_attempted=elevated_any,
                    restore=elevated_any,
                )

            if tools_used >= max_tools:
                return _with_gaps(
                    _failed("AI Research Cockpit tool budget exhausted without an answer"),
                    gap_clues,
                    elevated_attempted=elevated_any,
                )

            try:
                batch = self._registry.prepare_batch_result(
                    response.tool_calls,
                    max_calls=min(self._policy.max_tools_per_batch, remaining_tools),
                    allow_gaps=True,
                )
            except AgentToolValidationError:
                return _with_gaps(
                    _failed("Agent provider proposed an invalid tool batch"),
                    gap_clues,
                    elevated_attempted=elevated_any,
                )

            gap_clues.extend(batch.gaps)
            if tools_used + len(batch.prepared) > max_tools:
                return _with_gaps(
                    _failed("Agent provider proposed more tools than the turn budget allows"),
                    gap_clues,
                    elevated_attempted=elevated_any,
                )

            batch_results, err, elevated = self._run_batch(
                batch.prepared,
                tool_context=tool_context,
                started=started,
                tool_started=tool_started,
                cancelled=cancelled,
                progress=progress,
                approval=approval,
                total_bytes=total_bytes,
                seen_identities=seen_identities,
            )
            elevated_any = elevated_any or elevated
            if err is not None:
                return _with_gaps(err, gap_clues, elevated_attempted=elevated_any, restore=elevated)
            assert batch_results is not None
            by_id = {r.call_id: r for r in batch_results}
            for call in response.tool_calls:
                result = by_id.get(call.call_id)
                if result is None:
                    continue  # gap / skipped unregistered
                all_calls.append(call)
                all_results.append(result)
                total_bytes += result.serialized_size()
            tools_used += len(batch_results)

        return _with_gaps(
            _failed("AI Research Cockpit round budget exhausted without an answer"),
            gap_clues,
            elevated_attempted=elevated_any,
        )

    def _run_batch(
        self,
        prepared: tuple,
        *,
        tool_context: AgentToolExecutionContext,
        started: float,
        tool_started: float,
        cancelled: Callable[[], bool],
        progress: ProgressCallback,
        approval: ApprovalCallback | None,
        total_bytes: int,
        seen_identities: set[tuple[str, bytes]],
    ) -> tuple[list[AgentToolExecutionResult] | None, AgentTurnResult | None, bool]:
        results: list[AgentToolExecutionResult] = []
        running_bytes = total_bytes
        elevated_attempted = False
        for call in prepared:
            if cancelled():
                return None, _cancelled(), elevated_attempted
            try:
                identity = (call.name.value, canonical_json_bytes(call.arguments))
            except (TypeError, ValueError):
                return (
                    None,
                    _failed("Agent tool arguments contain unsupported values"),
                    elevated_attempted,
                )
            if identity in seen_identities:
                return (
                    None,
                    _failed("Agent provider proposed a duplicate tool call in this turn"),
                    elevated_attempted,
                )
            seen_identities.add(identity)

            definition = call.tool.definition
            if definition.approval is AgentToolApproval.PER_CALL:
                elevated_attempted = True
                req = AgentApprovalRequest(
                    call_id=call.call_id,
                    tool_name=call.name.value,
                    arg_summary=_arg_summary(call),
                    implication=_implication(definition.side_effect),
                    side_effect=definition.side_effect,
                )
                progress(f"AI Research Cockpit · confirm {call.name.value}…")
                approved = True if approval is None else bool(approval(req))
                if not approved:
                    results.append(
                        AgentToolExecutionResult.create(
                            call_id=call.call_id,
                            name=call.name,
                            status=AgentToolExecutionStatus.UNAVAILABLE,
                            data=None,
                            error_code="TOOL_DENIED",
                            error_message="Operator declined elevated/external tool",
                            warnings=("EXTERNAL_OR_ELEVATED_DECLINED",),
                            provenance=AgentToolProvenance(source=call.name.value),
                            side_effect=definition.side_effect,
                        )
                    )
                    continue

            progress(f"AI Research Cockpit · tool {call.name.value}…")
            result = self._execute_tool(call, tool_context, started, tool_started)
            if isinstance(result, AgentTurnResult):
                # Promote post-approve elevated failure to restore flag
                if elevated_attempted:
                    result = replace_restore(result, True)
                return None, result, elevated_attempted
            if (
                definition.side_effect is not AgentToolSideEffect.NONE
                and result.status
                in {
                    AgentToolExecutionStatus.FAILED,
                    AgentToolExecutionStatus.UNAVAILABLE,
                }
                and result.error_code != "TOOL_DENIED"
            ):
                # Post-approve fail: fail closed turn with restore (ADR-065)
                return (
                    None,
                    AgentTurnResult(
                        status=AgentTurnStatus.FAILED,
                        error_message=result.error_message
                        or "Elevated/external tool failed after approval",
                        restore_last_good=True,
                        elevated_attempted=True,
                    ),
                    True,
                )
            size = result.serialized_size()
            if size > call.tool.definition.max_result_bytes:
                return (
                    None,
                    _failed("Agent tool result exceeded its size limit"),
                    elevated_attempted,
                )
            running_bytes += size
            if running_bytes > self._policy.max_total_result_bytes:
                return (
                    None,
                    _failed("Agent tool results exceeded the turn size limit"),
                    elevated_attempted,
                )
            results.append(result)
        return results, None, elevated_attempted

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
        except AgentModelMalformedResponseError as exc:
            detail = str(exc).strip() or "malformed response"
            return _failed(f"Agent provider returned an invalid response: {detail}")
        except AgentModelTransportError as exc:
            detail = str(exc).strip() or "transport failed"
            return _failed(f"Agent provider transport failed: {detail}")
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            return _failed(f"Agent provider failed unexpectedly: {detail}")

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
                side_effect=call.tool.definition.side_effect,
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
                side_effect=call.tool.definition.side_effect,
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
                side_effect=call.tool.definition.side_effect,
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
    *,
    tools_offered: bool = False,
    gap_clues: tuple[AgentToolGapClue, ...] = (),
    elevated_attempted: bool = False,
) -> AgentTurnResult:
    text = response.text.strip()
    extra: list[str] = list(warnings)
    if response.finish_reason == "length":
        extra.append("Model answer reached the output limit")
    if tools_offered and not tool_results and not gap_clues:
        extra.append(
            "TOOLS_NOT_USED: Model answered without calling any registered tools. "
            "If the question needs broker desk, dashboard, or re-judge data not in "
            "context, re-ask and expect a tool call — or design a new OUR tool "
            "(TOOL_GAP clue)."
        )
    if tools_offered and not tool_results and not gap_clues and _looks_like_planning_only(text):
        return AgentTurnResult(
            status=AgentTurnStatus.FAILED,
            error_message=(
                "Model returned a plan instead of using tools or answering from "
                "Judge context. Re-ask, or note TOOL_GAP: we may need a ticker→top "
                "brokers tool (get_broker_desk is desk-code centric, not stock-centric)."
            ),
        )
    # Denied elevated tools count as non-SUCCESS for PARTIAL honesty
    status = (
        AgentTurnStatus.PARTIAL
        if any(result.status is not AgentToolExecutionStatus.SUCCESS for result in tool_results)
        or gap_clues
        else AgentTurnStatus.SUCCESS
    )
    if status is AgentTurnStatus.PARTIAL and not tool_results and gap_clues:
        # PARTIAL requires tool_results — attach synthetic note via SUCCESS if answer only
        status = AgentTurnStatus.SUCCESS
    return AgentTurnResult(
        status=status,
        answer=response.text,
        context_reference=context_reference,
        provider=response.provider,
        model=response.model,
        response_id=response.response_id,
        warnings=tuple(dict.fromkeys(extra)),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        tool_results=tool_results,
        gap_clues=gap_clues,
        elevated_attempted=elevated_attempted,
    )


def _with_gaps(
    result: AgentTurnResult,
    gaps: list[AgentToolGapClue] | tuple[AgentToolGapClue, ...],
    *,
    elevated_attempted: bool = False,
    restore: bool = False,
) -> AgentTurnResult:
    from dataclasses import replace

    gap_t = tuple(gaps)
    extra_warn = tuple(g.operator_line() for g in gap_t)
    return replace(
        result,
        warnings=tuple(dict.fromkeys(result.warnings + extra_warn)),
        gap_clues=gap_t or result.gap_clues,
        elevated_attempted=elevated_attempted or result.elevated_attempted,
        restore_last_good=restore or result.restore_last_good,
    )


def replace_restore(result: AgentTurnResult, restore: bool) -> AgentTurnResult:
    from dataclasses import replace

    return replace(result, restore_last_good=restore, elevated_attempted=True)


def _arg_summary(call: PreparedAgentToolCall) -> str:
    try:
        raw = canonical_json_bytes(call.arguments).decode("utf-8")
    except Exception:
        raw = call.name.value
    if len(raw) > 120:
        return raw[:117] + "…"
    return raw


def _implication(side_effect: AgentToolSideEffect) -> str:
    if side_effect is AgentToolSideEffect.NETWORK_READ:
        return "Network leaves this machine · external research · does not change Action"
    if side_effect is AgentToolSideEffect.LOCAL_READ_ELEVATED:
        return "Local read-only allowlisted query · broader surface · does not change Action"
    return "Read-only · does not change Action"


def _looks_like_planning_only(text: str) -> bool:
    """Heuristic: final text is only a promise to look something up."""
    lowered = text.strip().lower()
    if len(lowered) > 280:
        return False
    starters = (
        "i'll ",
        "i will ",
        "let me ",
        "i am going to ",
        "i'm going to ",
        "saya akan ",
        "saya coba ",
        "mari saya ",
        "baik, saya ",
    )
    if not any(lowered.startswith(s) for s in starters):
        return False
    plan_verbs = (
        "check",
        "investigate",
        "look up",
        "look into",
        "identify",
        "cek",
        "periksa",
        "cari",
        "telusuri",
    )
    return any(v in lowered for v in plan_verbs)


def _failed(message: str) -> AgentTurnResult:
    return AgentTurnResult(status=AgentTurnStatus.FAILED, error_message=message)


def _cancelled() -> AgentTurnResult:
    return AgentTurnResult(status=AgentTurnStatus.CANCELLED, error_message="Agent turn cancelled")
