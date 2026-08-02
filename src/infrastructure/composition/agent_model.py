"""Optional agent-model composition with fail-soft configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.application.dto.accumulation_agent import (
    AgentModelUnavailableReason,
    AgentTurnPolicy,
)
from src.application.use_case.explain_accumulation_candidate_use_case import (
    ExplainAccumulationCandidateUseCase,
)
from src.infrastructure.ai.deepseek_agent_model import DeepSeekAgentModel
from src.infrastructure.ai.provider_config import resolve_ai_provider
from src.infrastructure.config.local_env import read_local_env_value


@dataclass(frozen=True)
class AgentComposition:
    use_case: ExplainAccumulationCandidateUseCase
    provider_available: bool
    configured_provider: str


def build_agent_composition(ai_config: object, *, provider: str | None = None) -> AgentComposition:
    explicit = provider
    if explicit is None and not os.getenv("AI_PROVIDER"):
        explicit = str(getattr(ai_config, "provider", "deepseek"))
    configured = resolve_ai_provider(explicit).strip().lower()
    enabled = bool(getattr(ai_config, "enabled", False))
    model = None
    reason = None
    if not enabled:
        reason = AgentModelUnavailableReason.DISABLED
    elif configured != "deepseek":
        reason = AgentModelUnavailableReason.UNSUPPORTED_PROVIDER
    else:
        api_key = (
            os.getenv("DEEPSEEK_API_KEY", "").strip()
            or (read_local_env_value("DEEPSEEK_API_KEY") or "").strip()
        )
        if not api_key:
            reason = AgentModelUnavailableReason.MISSING_CREDENTIAL
        else:
            model = DeepSeekAgentModel(api_key)
    use_case = ExplainAccumulationCandidateUseCase(
        model,
        AgentTurnPolicy(
            enabled=enabled,
            configured_provider=configured,
            model_unavailable_reason=reason,
        ),
    )
    return AgentComposition(use_case, model is not None, configured)
