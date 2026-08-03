"""TUI/CLI-safe re-export of agent data-honesty presentation helpers.

Application owns the pure normalization logic; adapters import through this
module so TUI non-composition modules never import ``src.application.services``
directly (architecture boundary guard).

Layer: Adapter (shared re-export)
"""

from __future__ import annotations

from src.application.services.agent_data_honesty import (
    AgentDataHonestyView,
    AgentDataNote,
    AgentNoteSeverity,
    format_agent_more_notes,
    format_agent_status_strip,
    normalize_agent_data_notes,
)

__all__ = [
    "AgentDataHonestyView",
    "AgentDataNote",
    "AgentNoteSeverity",
    "format_agent_more_notes",
    "format_agent_status_strip",
    "normalize_agent_data_notes",
]
