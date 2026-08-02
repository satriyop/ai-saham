"""Model boundary for optional, non-authoritative agent commentary."""

from typing import Protocol

from src.application.dto.accumulation_agent import AgentModelRequest, AgentModelResponse


class AgentModelError(RuntimeError):
    """Base normalized provider failure."""


class AgentModelAuthenticationError(AgentModelError):
    pass


class AgentModelTimeoutError(AgentModelError):
    pass


class AgentModelRateLimitError(AgentModelError):
    pass


class AgentModelUnavailableError(AgentModelError):
    pass


class AgentModelMalformedResponseError(AgentModelError):
    pass


class AgentModelTransportError(AgentModelError):
    pass


class AgentModelPort(Protocol):
    def generate(self, request: AgentModelRequest) -> AgentModelResponse: ...
