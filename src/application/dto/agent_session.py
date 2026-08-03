"""Process-local ephemeral agent session contracts (ADR-063)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class AgentReferenceCompatibility(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True)
class AgentSessionPolicy:
    """Locked ADR-063 budgets — do not raise without an ADR amendment."""

    enabled: bool
    max_turns: int = 8
    max_full_commentary_turns: int = 3
    max_fresh_tool_records: int = 4
    max_packed_bytes: int = 24 * 1024
    max_older_summary_chars: int = 1_500
    max_in_flight: int = 1

    def __post_init__(self) -> None:
        if self.max_turns != 8:
            raise ValueError("ADR-063 requires max_turns=8")
        if self.max_full_commentary_turns != 3:
            raise ValueError("ADR-063 requires max_full_commentary_turns=3")
        if self.max_fresh_tool_records != 4:
            raise ValueError("ADR-063 requires max_fresh_tool_records=4")
        if self.max_packed_bytes != 24 * 1024:
            raise ValueError("ADR-063 requires max_packed_bytes=24KiB")
        if self.max_older_summary_chars != 1_500:
            raise ValueError("ADR-063 requires max_older_summary_chars=1500")
        if self.max_in_flight != 1:
            raise ValueError("ADR-063 requires max_in_flight=1")


@dataclass(frozen=True)
class AgentCapabilityCertification:
    provider: str
    model_id: str
    system_prompt_version: str
    tool_schema_version: str
    evaluation_suite_version: str
    certified_on: date
    passed: bool

    def __post_init__(self) -> None:
        if not all(
            (
                self.provider.strip(),
                self.model_id.strip(),
                self.system_prompt_version.strip(),
                self.tool_schema_version.strip(),
                self.evaluation_suite_version.strip(),
            )
        ):
            raise ValueError("capability certification fields cannot be empty")


@dataclass(frozen=True)
class AgentSessionToolRecord:
    """Bounded memory of a prior tool result — references, not authority."""

    name: str
    status: str
    result_reference: str
    source_reference: str | None
    as_of: date | None
    schema_id: str | None
    subject: str | None
    context_reference: str
    compatibility: AgentReferenceCompatibility = AgentReferenceCompatibility.FRESH

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.result_reference.strip():
            raise ValueError("tool session record requires name and result_reference")
        if not self.context_reference.strip():
            raise ValueError("tool session record requires originating context_reference")


@dataclass(frozen=True)
class AgentSessionCommentaryTurn:
    turn_sequence: int
    turn_id: str
    question: str
    answer: str
    status: str
    context_reference: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.turn_sequence < 1:
            raise ValueError("turn_sequence must start at 1")
        if not self.turn_id.strip():
            raise ValueError("turn_id cannot be empty")
        if not self.context_reference.strip():
            raise ValueError("commentary turn requires context_reference")


@dataclass(frozen=True)
class AgentSessionState:
    session_id: str
    turn_count: int
    anchor_context_reference: str | None
    anchor_ticker: str | None
    anchor_schema_id: str | None
    commentary_turns: tuple[AgentSessionCommentaryTurn, ...]
    older_commentary_summary: str
    tool_records: tuple[AgentSessionToolRecord, ...]
    structural_warnings: tuple[str, ...]
    structural_failures: tuple[str, ...]
    in_flight: bool = False

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if self.turn_count < 0:
            raise ValueError("turn_count cannot be negative")


@dataclass(frozen=True)
class AgentSessionPack:
    """Model-facing session history block (non-authoritative commentary + refs)."""

    schema_id: str
    session_id: str
    next_turn_sequence: int
    current_context_reference: str
    current_ticker: str
    prior_commentary: tuple[AgentSessionCommentaryTurn, ...]
    older_commentary_summary: str
    fresh_tool_records: tuple[AgentSessionToolRecord, ...]
    stale_or_incompatible_tool_records: tuple[AgentSessionToolRecord, ...]
    structural_warnings: tuple[str, ...]
    structural_failures: tuple[str, ...]
    pack_warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_id != "agent_session.pack.v1":
            raise ValueError("unsupported agent session pack schema")
        if self.next_turn_sequence < 1:
            raise ValueError("next_turn_sequence must be >= 1")
