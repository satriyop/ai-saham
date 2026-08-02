"""DeepSeek transport for optional accumulation commentary."""

from __future__ import annotations

import json
from typing import Any

from src.application.dto.accumulation_agent import AgentModelRequest, AgentModelResponse
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
        try:
            response = self._client.chat.completions.create(
                model=self.default_model,
                messages=[
                    {"role": "system", "content": request.system_policy},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": request.user_text,
                                "context": request.context.canonical_payload()
                                | {"context_reference": request.context.context_reference},
                            },
                            ensure_ascii=False,
                            allow_nan=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                max_tokens=request.max_output_tokens,
                temperature=0.0,
                tool_choice="none",
                extra_body={"thinking": {"type": "disabled"}},
            )
        except Exception as exc:
            self._normalize_error(exc)
            raise AssertionError("unreachable")
        choices = getattr(response, "choices", None)
        if not choices:
            raise AgentModelMalformedResponseError("DeepSeek response has no choices")
        choice = choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason not in {"stop", "length"}:
            if finish_reason == "insufficient_system_resource":
                raise AgentModelUnavailableError("DeepSeek system resources unavailable")
            raise AgentModelMalformedResponseError(f"Unsupported finish reason: {finish_reason}")
        text = str(getattr(getattr(choice, "message", None), "content", "") or "").strip()
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
