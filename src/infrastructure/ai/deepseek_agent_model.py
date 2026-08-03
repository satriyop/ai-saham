"""DeepSeek transport for optional accumulation commentary."""

from __future__ import annotations

import json
import re
from typing import Any

from src.application.dto.accumulation_agent import (
    AgentModelRequest,
    AgentModelResponse,
    AgentModelResponseKind,
)
from src.application.dto.agent_tools import AgentModelToolCall, AgentModelToolChoice
from src.application.ports.agent_model import (
    AgentModelAuthenticationError,
    AgentModelMalformedResponseError,
    AgentModelRateLimitError,
    AgentModelTimeoutError,
    AgentModelTransportError,
    AgentModelUnavailableError,
)

# DeepSeek occasionally emits closed-tool proposals as DSML text in ``content``
# instead of structured ``message.tool_calls``. Never show that markup as the
# operator-facing answer.
_DSML_INVOKE_RE = re.compile(
    r'invoke\s+name\s*=\s*"(?P<name>[^"]+)"\s*>(?P<body>.*?)'
    r"(?=invoke\s+name\s*=|$)",
    re.IGNORECASE | re.DOTALL,
)
_DSML_PARAM_RE = re.compile(
    r'parameter\s+name\s*=\s*"(?P<key>[^"]+)"[^>]*>\s*(?P<val>.*?)\s*</',
    re.IGNORECASE | re.DOTALL,
)


class DeepSeekAgentModel:
    provider = "deepseek"
    default_model = "deepseek-v4-flash"

    def __init__(self, api_key: str, *, client: Any | None = None) -> None:
        if not api_key.strip():
            raise ValueError("DeepSeek API key cannot be empty")
        if client is None:
            import openai

            client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
                timeout=10.0,
                max_retries=0,
            )
        self._client = client

    def generate(self, request: AgentModelRequest) -> AgentModelResponse:
        messages = self._messages(request)
        kwargs: dict[str, Any] = {
            "model": self.default_model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": 0.0,
            "tool_choice": request.tool_choice.value,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
        if request.tool_definitions:
            kwargs["tools"] = [self._tool_definition(item) for item in request.tool_definitions]
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            self._normalize_error(exc)
            raise AssertionError("unreachable")
        choices = getattr(response, "choices", None)
        if not choices:
            raise AgentModelMalformedResponseError("DeepSeek response has no choices")
        choice = choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        message = getattr(choice, "message", None)
        text = _message_text(message)
        model_name = str(getattr(response, "model", None) or self.default_model)
        response_id = getattr(response, "id", None)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)

        if finish_reason == "insufficient_system_resource":
            raise AgentModelUnavailableError("DeepSeek system resources unavailable")

        wants_tools = request.tool_choice is AgentModelToolChoice.AUTO
        raw_tool_calls = getattr(message, "tool_calls", None) if message is not None else None
        has_tool_payload = bool(raw_tool_calls)
        dsml_markup = looks_like_tool_markup(text)

        # Prefer tool calls when the provider signals them or when auto mode
        # returns tool_calls even if finish_reason is missing/stop (API drift).
        if wants_tools and (finish_reason == "tool_calls" or has_tool_payload):
            try:
                calls = self._tool_calls(message)
            except AgentModelMalformedResponseError:
                # Structured tools unusable — try DSML-in-content, else plain text.
                if dsml_markup:
                    try:
                        calls = parse_dsml_tool_calls(text)
                    except AgentModelMalformedResponseError:
                        if text and not dsml_markup:
                            pass
                        else:
                            raise
                    else:
                        return AgentModelResponse(
                            text="",
                            provider=self.provider,
                            model=model_name,
                            response_id=response_id,
                            finish_reason=finish_reason or "tool_calls",
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            kind=AgentModelResponseKind.TOOL_CALLS,
                            tool_calls=calls,
                        )
                if text and not dsml_markup:
                    return AgentModelResponse(
                        text=text,
                        provider=self.provider,
                        model=model_name,
                        response_id=response_id,
                        finish_reason=finish_reason or "stop",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                raise
            return AgentModelResponse(
                text="",
                provider=self.provider,
                model=model_name,
                response_id=response_id,
                finish_reason=finish_reason or "tool_calls",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                kind=AgentModelResponseKind.TOOL_CALLS,
                tool_calls=calls,
            )

        # Auto mode with empty structured tools but DSML body → treat as tool batch.
        if wants_tools and dsml_markup and not has_tool_payload:
            calls = parse_dsml_tool_calls(text)
            return AgentModelResponse(
                text="",
                provider=self.provider,
                model=model_name,
                response_id=response_id,
                finish_reason="tool_calls",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                kind=AgentModelResponseKind.TOOL_CALLS,
                tool_calls=calls,
            )

        if finish_reason == "tool_calls" and not wants_tools:
            # Final call must be an answer — never surface tool markup.
            if text and not dsml_markup:
                return AgentModelResponse(
                    text=text,
                    provider=self.provider,
                    model=model_name,
                    response_id=response_id,
                    finish_reason="stop",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            raise AgentModelMalformedResponseError("DeepSeek proposed tools after tool_choice=none")

        if finish_reason not in {None, "stop", "length", "end_turn"}:
            if finish_reason == "content_filter":
                raise AgentModelMalformedResponseError("DeepSeek content filter blocked the answer")
            raise AgentModelMalformedResponseError(f"Unsupported finish reason: {finish_reason!r}")
        if not text:
            raise AgentModelMalformedResponseError(
                f"DeepSeek response text is empty (finish_reason={finish_reason!r})"
            )
        if dsml_markup:
            # stop + DSML content (common on forced final) — never paint as answer.
            raise AgentModelMalformedResponseError(
                "DeepSeek returned tool markup instead of a final prose answer"
            )
        return AgentModelResponse(
            text=text,
            provider=self.provider,
            model=model_name,
            response_id=response_id,
            finish_reason=finish_reason or "stop",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    @staticmethod
    def _tool_definition(definition: Any) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        for field in definition.arguments:
            schema: dict[str, Any] = {
                "type": field.value_type.value,
                "description": field.description,
            }
            if field.enum_values:
                schema["enum"] = list(field.enum_values)
            properties[field.name] = schema
        return {
            "type": "function",
            "function": {
                "name": definition.name.value,
                "description": definition.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [field.name for field in definition.arguments],
                    "additionalProperties": False,
                },
            },
        }

    @staticmethod
    def _tool_calls(message: Any) -> tuple[AgentModelToolCall, ...]:
        raw_calls = getattr(message, "tool_calls", None)
        if not raw_calls or not 1 <= len(raw_calls) <= 2:
            raise AgentModelMalformedResponseError(
                "DeepSeek tool response requires one or two calls"
            )
        calls: list[AgentModelToolCall] = []
        for raw in raw_calls:
            raw_type = getattr(raw, "type", None)
            if raw_type not in {None, "function"}:
                raise AgentModelMalformedResponseError("DeepSeek returned a non-function tool")
            function = getattr(raw, "function", None)
            name = str(getattr(function, "name", "") or "")
            call_id = str(getattr(raw, "id", "") or "")
            arguments = getattr(function, "arguments", None)
            if isinstance(arguments, dict):
                arguments_json = json.dumps(arguments, separators=(",", ":"), ensure_ascii=False)
            else:
                arguments_json = str(arguments or "").strip()
            if not arguments_json:
                arguments_json = "{}"
            try:
                calls.append(
                    AgentModelToolCall(
                        call_id=call_id or f"call-{len(calls) + 1}",
                        name=name,
                        arguments_json=arguments_json,
                    )
                )
            except ValueError as exc:
                raise AgentModelMalformedResponseError(
                    f"DeepSeek returned an invalid tool call: {exc}"
                ) from exc
        return tuple(calls)

    @staticmethod
    def _messages(request: AgentModelRequest) -> list[dict[str, Any]]:
        from src.application.dto.agent_tools import canonical_json_value

        payload: dict[str, Any] = {
            "question": request.user_text,
            "context": request.context.canonical_payload()
            | {"context_reference": request.context.context_reference},
        }
        if request.session_pack is not None:
            # Session history is non-authoritative commentary + exact references only.
            payload["session"] = canonical_json_value(request.session_pack)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.system_policy},
            {
                "role": "user",
                "content": json.dumps(
                    payload,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ),
            },
        ]
        if request.prior_tool_calls:
            # Interleave call/result pairs so multi-round history stays ordered
            # (ADR-064). L1 single-batch still works as consecutive pairs.
            for call, result in zip(request.prior_tool_calls, request.tool_results, strict=True):
                messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": call.call_id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": call.arguments_json,
                                },
                            }
                        ],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.call_id,
                        "content": json.dumps(
                            result.canonical_payload(),
                            ensure_ascii=False,
                            allow_nan=False,
                            separators=(",", ":"),
                        ),
                    }
                )
        return messages

    @staticmethod
    def _normalize_error(exc: Exception) -> None:
        name = type(exc).__name__
        if name == "AuthenticationError":
            raise AgentModelAuthenticationError("DeepSeek authentication failed") from exc
        if name == "APITimeoutError" or isinstance(exc, TimeoutError):
            raise AgentModelTimeoutError("DeepSeek timed out") from exc
        if name == "RateLimitError":
            raise AgentModelRateLimitError("DeepSeek rate limited") from exc
        if name in {"APIConnectionError", "InternalServerError"}:
            raise AgentModelUnavailableError("DeepSeek unavailable") from exc
        raise AgentModelTransportError("DeepSeek request failed") from exc


def _message_text(message: Any) -> str:
    """Normalize provider message content (string or content-part list) to text."""
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
                continue
            text = getattr(item, "text", None) or getattr(item, "content", None)
            if text:
                parts.append(str(text))
        return "\n".join(part.strip() for part in parts if part and str(part).strip()).strip()
    return str(content).strip()


def looks_like_tool_markup(text: str) -> bool:
    """True when content is tool-call markup (DSML / invoke blocks), not prose."""
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    has_invoke = bool(re.search(r"invoke\s+name\s*=", raw, re.I))
    has_param = bool(re.search(r"parameter\s+name\s*=", raw, re.I))
    if has_invoke and has_param:
        return True
    if "tool_calls" in low and has_invoke:
        return True
    if "dsml" in low and has_invoke:
        return True
    return False


def parse_dsml_tool_calls(text: str) -> tuple[AgentModelToolCall, ...]:
    """Parse DeepSeek DSML-style invoke blocks into closed tool calls (max 2)."""
    calls: list[AgentModelToolCall] = []
    for index, match in enumerate(_DSML_INVOKE_RE.finditer(text or ""), start=1):
        name = match.group("name").strip()
        body = match.group("body") or ""
        args: dict[str, str] = {}
        for param in _DSML_PARAM_RE.finditer(body):
            key = param.group("key").strip()
            val = param.group("val").strip()
            # Drop trailing markup debris inside the value capture.
            val = re.split(r"[|\n]", val, maxsplit=1)[0].strip()
            val = re.sub(r"\s*<.*$", "", val).strip()
            if key:
                args[key] = val
        if not name:
            continue
        try:
            calls.append(
                AgentModelToolCall(
                    call_id=f"dsml-{index}",
                    name=name,
                    arguments_json=json.dumps(args, separators=(",", ":"), ensure_ascii=False),
                )
            )
        except ValueError as exc:
            raise AgentModelMalformedResponseError(
                f"DeepSeek DSML tool call invalid: {exc}"
            ) from exc
    if not 1 <= len(calls) <= 2:
        raise AgentModelMalformedResponseError(
            "DeepSeek DSML tool markup requires one or two invoke blocks"
        )
    return tuple(calls)
