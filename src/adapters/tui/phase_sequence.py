"""Present closed-session setup phase ledger sequence (ADR-058 read path).

Display-only production memory. Does not re-score Action/Signal/Risk and does
not write the ledger.

UI contracts (match docs/design/tui-judge-desk.html):
- Collapse consecutive same-phase days into **runs**, not a day diary.
- Arrow = run story (e.g. DIST (16d) → ACCUM (2d)), never A→A→A→…
- Detail = one line per run; no full daily dump by default.
- Single production-memory footer.

Layer: Adapter (pure format)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.adapters.tui.theme import OC


@dataclass(frozen=True)
class PhaseSequenceFact:
    """One prior closed-session phase fact for Judge display."""

    phase: str
    as_of: str = ""


@dataclass(frozen=True)
class PhaseRun:
    """Collapsed consecutive same-phase sessions (oldest→newest within run)."""

    phase: str
    sessions: int
    first_as_of: str
    last_as_of: str

    def label(self) -> str:
        """Short arrow label: PHASE (Nd) or PHASE when single day."""
        n = max(1, int(self.sessions))
        if n <= 1:
            return self.phase
        return f"{self.phase} ({n}d)"

    def detail_line(self) -> str:
        if self.sessions <= 1:
            if self.first_as_of:
                return f"{self.phase} · 1 session · {self.first_as_of}"
            return f"{self.phase} · 1 session"
        span = _date_span(self.first_as_of, self.last_as_of)
        return f"{self.phase} · {self.sessions} sessions · {span}"


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


def collapse_phase_runs(facts: Sequence[PhaseSequenceFact]) -> tuple[PhaseRun, ...]:
    """Collapse consecutive identical phases into runs (oldest→newest)."""
    runs: list[PhaseRun] = []
    for fact in facts:
        phase = (fact.phase or "").strip()
        if not phase:
            continue
        as_of = (fact.as_of or "").strip()
        if runs and runs[-1].phase == phase:
            prev = runs[-1]
            runs[-1] = PhaseRun(
                phase=phase,
                sessions=prev.sessions + 1,
                first_as_of=prev.first_as_of or as_of,
                last_as_of=as_of or prev.last_as_of,
            )
        else:
            runs.append(
                PhaseRun(
                    phase=phase,
                    sessions=1,
                    first_as_of=as_of,
                    last_as_of=as_of,
                )
            )
    return tuple(runs)


def format_phase_sequence_section(
    facts: Sequence[PhaseSequenceFact] | None,
    *,
    current_phase: str | None = None,
    unavailable_reason: str | None = None,
) -> list[str]:
    """Multi-line Phase sequence block for the Judge desk (design-aligned).

    Empty facts + no unavailable_reason → honest empty history cue.
    unavailable_reason → cannot query without inventing.
    """
    lines = [f"[{OC.purple}]Phase sequence · ledger[/]"]
    if unavailable_reason:
        lines.append(f"  {unavailable_reason}")
        lines.append("  [dim]production memory · not a re-score[/]")
        return lines

    items = list(facts or ())
    if not items:
        lines.append("  no closed-session phase history")
        lines.append("  [dim]production memory · not a re-score[/]")
        return lines

    runs = collapse_phase_runs(items)
    if not runs:
        lines.append("  no closed-session phase history")
        lines.append("  [dim]production memory · not a re-score[/]")
        return lines

    # One-line story: collapsed runs only (never day-level A→A→A).
    if len(runs) == 1 and runs[0].sessions > 1:
        r0 = runs[0]
        lines.append(
            f"  {r0.phase} only  [dim]({r0.sessions} sessions · "
            f"{_date_span(r0.first_as_of, r0.last_as_of)})[/]"
        )
    else:
        lines.append("  " + " → ".join(r.label() for r in runs))

    # One detail line per run (not per day).
    for run in runs:
        lines.append(f"  · {run.detail_line()}")

    cur = (current_phase or "").strip()
    if cur and cur not in {"—", "-", "NONE", "none"}:
        lines.append(f"  [bold]now[/] {cur}  [dim](board · not ledger-written here)[/]")

    # Transition count when useful
    if len(runs) >= 2:
        last_change = runs[-1].first_as_of or "—"
        lines.append(f"  [dim]{len(runs) - 1} transition(s) · last change {last_change}[/]")

    lines.append("  [dim]production memory · not a re-score[/]")
    return lines


def _date_span(first: str, last: str) -> str:
    """Compact date range for run detail."""
    start = (first or "").strip()
    end = (last or "").strip()
    if not start and not end:
        return "—"
    if not start:
        return end
    if not end or start == end:
        return start
    # Same year: 2026-07-01 → 07-24
    if len(start) >= 10 and len(end) >= 10 and start[:5] == end[:5]:
        return f"{start} → {end[5:]}"
    return f"{start} → {end}"
