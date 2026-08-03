"""DeepSeek transport for optional accumulation commentary."""

from __future__ import annotations

import json
from typing import Any

from src.application.dto.accumulation_agent import (
    AgentModelRequest,
    AgentModelResponse,
    AgentModelResponseKind,
)
from src.application.dto.agent_tools import AgentModelToolCall
from src.application.ports.agent_model import (
    AgentModelAuthenticationError,
    AgentModelMalformedResponseError,
    AgentModelRateLimitError,
    AgentModelTimeoutError,
    AgentModelTransportError,
    AgentModelUnavailableError,
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
        if finish_reason == "tool_calls":
            calls = self._tool_calls(message)
            return AgentModelResponse(
                text="",
                provider=self.provider,
                model=str(getattr(response, "model", None) or self.default_model),
                response_id=getattr(response, "id", None),
                finish_reason=finish_reason,
                input_tokens=getattr(getattr(response, "usage", None), "prompt_tokens", None),
                output_tokens=getattr(getattr(response, "usage", None), "completion_tokens", None),
                kind=AgentModelResponseKind.TOOL_CALLS,
                tool_calls=calls,
            )
        if finish_reason not in {"stop", "length"}:
            if finish_reason == "insufficient_system_resource":
                raise AgentModelUnavailableError("DeepSeek system resources unavailable")
            raise AgentModelMalformedResponseError(f"Unsupported finish reason: {finish_reason}")
        text = str(getattr(message, "content", "") or "").strip()
        if not text:
            raise AgentModelMalformedResponseError("DeepSeek response text is empty")
        usage = getattr(response, "usage", None)
        return AgentModelResponse(
            text=text,
            provider=self.provider,
            model=str(getattr(response, "model", None) or self.default_model),
            response_id=getattr(response, "id", None),
            finish_reason=finish_reason,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
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
            if getattr(raw, "type", None) != "function":
                raise AgentModelMalformedResponseError("DeepSeek returned a non-function tool")
            function = getattr(raw, "function", None)
            try:
                calls.append(
                    AgentModelToolCall(
                        call_id=str(getattr(raw, "id", "") or ""),
                        name=str(getattr(function, "name", "") or ""),
                        arguments_json=str(getattr(function, "arguments", "") or ""),
                    )
                )
            except ValueError as exc:
                raise AgentModelMalformedResponseError(
                    "DeepSeek returned an invalid tool call"
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
                        for call in request.prior_tool_calls
                    ],
                }
            )
            messages.extend(
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
                for result in request.tool_results
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
