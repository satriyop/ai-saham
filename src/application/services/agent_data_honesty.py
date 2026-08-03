"""Normalize agent data-honesty warnings into ranked operator notes.

Layer: Application (pure)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class AgentNoteSeverity(str, Enum):
    WARN = "WARN"
    INFO = "INFO"


@dataclass(frozen=True)
class AgentDataNote:
    code: str
    severity: AgentNoteSeverity
    title: str
    do_line: str
    detail: str

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.title.strip() or not self.do_line.strip():
            raise ValueError("agent data note requires code, title, and do_line")


@dataclass(frozen=True)
class AgentDataHonestyView:
    """Display model: primary strip notes + collapsed technical remainder."""

    primary: tuple[AgentDataNote, ...]
    more: tuple[AgentDataNote, ...]
    raw_count: int

    @property
    def empty(self) -> bool:
        return not self.primary and not self.more


_RISK_LAG = re.compile(
    r"Risk snapshot\s+(\S+)\s+differs from decision as-of\s+(\S+)",
    re.I,
)
_AUTHORITY = re.compile(
    r"Incomplete signal authority|not source-authoritative|authority coverage",
    re.I,
)
_LATE_WITHIN = re.compile(
    r"SESSION_ALIGNED_LATE_WITHIN_LAG|within the expected .*settlement|LATE rather than STALE|"
    r"observed_through is \d+ trading session",
    re.I,
)
_PROVIDER_CUTOFF = re.compile(r"Provider cutoff", re.I)
_BANDAR = re.compile(r"^bandar_detector$", re.I)


def normalize_agent_data_notes(
    warnings: tuple[str, ...],
    *,
    max_primary: int = 3,
) -> AgentDataHonestyView:
    """Map raw warning strings to ranked notes with operator guidance.

    Dedupes by code (first detail wins). Severity ranks WARN above INFO.
    Primary strip shows at most ``max_primary`` notes; remainder is ``more``.
    """
    if max_primary < 1:
        raise ValueError("max_primary must be >= 1")
    raw = tuple(dict.fromkeys(item.strip() for item in warnings if item and item.strip()))
    by_code: dict[str, AgentDataNote] = {}
    for raw_line in raw:
        note = _classify(raw_line)
        if note.code not in by_code:
            by_code[note.code] = note
    ranked = sorted(
        by_code.values(),
        key=lambda n: (0 if n.severity is AgentNoteSeverity.WARN else 1, n.code),
    )
    primary = tuple(ranked[:max_primary])
    more = tuple(ranked[max_primary:])
    return AgentDataHonestyView(primary=primary, more=more, raw_count=len(raw))


def format_agent_status_strip(
    *,
    turn_ok: bool,
    ticker: str,
    as_of: str,
    notes: AgentDataHonestyView,
) -> str:
    """Single-block status strip for agent stage header."""
    turn = "OK" if turn_ok else "FAIL"
    line1 = f"Turn  {turn} · {ticker or '—'} · as-of {as_of or '—'}"
    if notes.empty:
        return line1 + "\nData  clean · no honesty notes"
    chips: list[str] = []
    for note in notes.primary:
        chips.append(note.title)
    more_n = len(notes.more)
    data_line = "Data  " + " · ".join(chips)
    if more_n:
        data_line += f" · +{more_n} more"
    guide_lines = [f"  {note.code}: {note.do_line}" for note in notes.primary]
    return "\n".join([line1, data_line, *guide_lines])


def format_agent_more_notes(notes: AgentDataHonestyView) -> str:
    if not notes.more:
        return ""
    lines = [f"More data notes ({len(notes.more)})"]
    for note in notes.more:
        lines.append(f"  [{note.severity.value}] {note.code} — {note.title}")
        lines.append(f"    Do: {note.do_line}")
        if note.detail and note.detail != note.title:
            lines.append(f"    Detail: {note.detail}")
    return "\n".join(lines)


def _classify(raw: str) -> AgentDataNote:
    if _RISK_LAG.search(raw):
        return AgentDataNote(
            code="RISK_SNAPSHOT_LAG",
            severity=AgentNoteSeverity.WARN,
            title="Risk lag",
            do_line=(
                "Treat Risk as secondary for this decision date; refresh risk "
                "inputs for the decision as-of when you need alignment (r / fetch). "
                "Do not assume Action is wrong only from this note."
            ),
            detail=raw,
        )
    if _AUTHORITY.search(raw):
        return AgentDataNote(
            code="AUTHORITY_INCOMPLETE",
            severity=AgentNoteSeverity.WARN,
            title="Authority incomplete",
            do_line=(
                "Accept lower signal authority for now, or fix source authority "
                "pipeline later. Re-asking the model will not restore authority."
            ),
            detail=raw,
        )
    if _LATE_WITHIN.search(raw) or _PROVIDER_CUTOFF.search(raw):
        return AgentDataNote(
            code="SETTLEMENT_LATE_WITHIN_LAG",
            severity=AgentNoteSeverity.INFO,
            title="Settlement late (within lag)",
            do_line=(
                "Normal settle window — wait next session or explicit fetch if you "
                "need fresher cache. Not STALE; avoid panic re-fetch loops."
            ),
            detail=raw,
        )
    if _BANDAR.search(raw) or "bandar_detector" in raw.lower():
        return AgentDataNote(
            code="BANDAR_DIAGNOSTIC",
            severity=AgentNoteSeverity.INFO,
            title="Bandar diagnostic",
            do_line=(
                "Optional diagnostic only; does not change Action. Inspect ticker "
                "dashboard/bandar cache if you care about this branch."
            ),
            detail=raw,
        )
    # Token-like bare codes from readiness / unassessed contributors
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,40}", raw):
        return AgentDataNote(
            code="DATA_BRANCH",
            severity=AgentNoteSeverity.INFO,
            title=raw.replace("_", " ").lower(),
            do_line=(
                "Named data branch incomplete or unassessed. No Action change; "
                "inspect Judge/detail or cache if needed."
            ),
            detail=raw,
        )
    return AgentDataNote(
        code="DATA_NOTE",
        severity=AgentNoteSeverity.INFO,
        title="Data note",
        do_line="Review on Judge/detail; agent cannot change deterministic Action.",
        detail=raw,
    )
