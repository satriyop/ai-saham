"""TUI-safe re-export of Research Cockpit stage-context wiring (ADR-066).

Application owns projection builders and raw-input types; the TUI assembles
raw inputs and calls ``build_agent_stage_context`` only. Adapters import
through this module so non-composition TUI modules never import
``src.application.services`` directly (architecture boundary guard).

Layer: Adapter (shared re-export)
"""

from __future__ import annotations

from src.application.services.agent_accum_screen_context import AgentAccumScreenRawInput
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    AgentContextUnavailableError,
)
from src.application.services.agent_plan_swing_context import AgentPlanSwingRawInput
from src.application.services.agent_preopen_screen_context import (
    AgentPreOpenScreenRawInput,
)
from src.application.services.agent_stage_context import build_agent_stage_context

__all__ = [
    "AgentAccumScreenRawInput",
    "AgentContextInvariantError",
    "AgentContextUnavailableError",
    "AgentPlanSwingRawInput",
    "AgentPreOpenScreenRawInput",
    "build_agent_stage_context",
]
