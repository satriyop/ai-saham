"""Paper notebook log result for TUI plan-stage handoff (ADR-054).

Thin adapter DTO — journal write policy stays in application use cases.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaperLogResult:
    """Outcome of an explicit paper journal confirm from the plan desk."""

    ticker: str
    written: bool
    message: str
    planned_entry: str = ""
    planned_stop: str = ""
    planned_target: str = ""
    refused: bool = False
    plan_id: str = ""

    @property
    def ok(self) -> bool:
        return not self.refused and self.written


def refuse_paper_log(ticker: str, reason: str) -> PaperLogResult:
    """Honest refuse (no write attempted)."""
    t = (ticker or "—").strip().upper() or "—"
    return PaperLogResult(
        ticker=t,
        written=False,
        message=reason,
        refused=True,
    )
