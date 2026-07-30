"""Present closed-session setup phase ledger sequence (ADR-058 read path).

Display-only production memory. Does not re-score Action/Signal/Risk and does
not write the ledger.

Layer: Adapter (pure format)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PhaseSequenceFact:
    """One prior closed-session phase fact for Judge display."""

    phase: str
    as_of: str = ""


def facts_from_ledger_rows(rows: Sequence[Any]) -> tuple[PhaseSequenceFact, ...]:
    """Map SetupPhaseLedgerRow-like objects → display facts (oldest→newest)."""
    out: list[PhaseSequenceFact] = []
    for row in rows:
        phase = getattr(row, "phase", None)
        if phase is None:
            continue
        phase_s = str(getattr(phase, "value", phase) or "").strip()
        if not phase_s:
            continue
        as_of = getattr(row, "as_of_date", None)
        as_of_s = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of or "")
        out.append(PhaseSequenceFact(phase=phase_s, as_of=as_of_s))
    return tuple(out)


def format_phase_sequence_section(
    facts: Sequence[PhaseSequenceFact] | None,
    *,
    current_phase: str | None = None,
    unavailable_reason: str | None = None,
) -> list[str]:
    """Multi-line Phase sequence block for the Judge desk.

    Empty facts + no unavailable_reason → honest empty history cue.
    unavailable_reason → cannot query (missing as_of / loader) without inventing.
    """
    # Timeline language (Verdict mast companion — ADR-058 read-only).
    lines = ["[#9b8fb8]Phase sequence · ledger timeline[/]"]
    if unavailable_reason:
        lines.append(f"  {unavailable_reason}")
        lines.append("  [dim]production memory · not a re-score[/]")
        return lines

    items = list(facts or ())
    if not items:
        lines.append("  no closed-session phase history")
        lines.append("  [dim]production memory · not a re-score[/]")
        return lines

    # Arrow timeline (oldest → newest); last node is most recent ledger fact.
    nodes = [f.phase for f in items]
    lines.append("  " + " → ".join(nodes))
    for fact in items:
        if fact.as_of:
            lines.append(f"  · {fact.as_of}  {fact.phase}")
        else:
            lines.append(f"  · {fact.phase}")

    cur = (current_phase or "").strip()
    if cur and cur not in {"—", "-", "NONE", "none"}:
        lines.append(f"  [bold]now[/] {cur}  [dim](board · not ledger-written here)[/]")

    lines.append("  [dim]production memory · not a re-score[/]")
    return lines
