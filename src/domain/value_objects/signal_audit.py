"""
Signal audit value objects.

Phase 0 observability artifacts for the SignalEngine refactor. These make the
current flat-weighted composite scoring measurable without changing production
scoring. A SignalAuditReport captures, per factor: presence, raw context value,
component score (0–100), configured vs. active (renormalized) weight, and each
factor's weighted contribution to the composite total.

The renormalized_score field is a preview of Phase 4 behavior (missing factors
excluded from the weight pool rather than defaulting to neutral 50). It is
informational only — it does not affect the production score.

Layer: Domain
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SignalAuditEntry:
    """Per-factor audit row for one ticker's signal assessment."""

    factor: str
    present: bool
    raw_value: str            # human-readable context value, e.g. "broad_score=4" or "None"
    component_score: float    # 0–100 (50.0 when missing/neutral fill)
    configured_weight: float  # raw weight from YAML (before renormalization)
    active_weight: float      # renormalized weight (what the current engine uses)
    weighted_contribution: float  # active_weight * component_score


@dataclass(frozen=True)
class SignalAuditReport:
    """Full audit of the SignalEngine inputs for one ticker."""

    ticker: str
    snapshot_date: date
    entries: tuple[SignalAuditEntry, ...]
    final_score: int
    strength: str
    entry_quality: str
    coverage_warning: str | None
    factors_present: int
    factors_missing: int
    renormalized_score: int  # preview: score if missing factors excluded from weight pool
