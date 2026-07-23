"""Repository port for observation-linked risk assessment detail rows.

Ownership rules (child table ``observation_risk_assessments``):

1. Parent ``candidate_observations`` owns the capture event.
2. Child is 0..1 detail for that observation — never a rival "screen result".
3. Write only at capture with parent; never a cron without parent.
4. Source of truth for **full** RiskAssessment = child JSON; payload
   ``candidate.risk_*`` stays lean summary.
5. Name is ``observation_risk_assessments`` — not risk_timeseries.
6. Research authority NONE until a later ADR.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class ObservationRiskAssessmentRecord:
    ticker: str
    snapshot_date: date
    workflow: str
    window_sessions: int
    data_as_of_date: date
    config_hash: str
    assessed_at: datetime
    schema_version: int
    risk_assessment_json: dict
    trade_setup_json: dict | None
    gate_triggered: str | None
    setup_action: str | None


class ObservationRiskAssessmentRepository(Protocol):
    def save_many(self, records: list[ObservationRiskAssessmentRecord]) -> int:
        """Upsert risk assessment detail rows by canonical observation identity."""
        ...
