"""
Signal audit value objects.

- These value objects describe the archived six-factor baseline.
- final_score is the archived neutral-fill baseline score.
- renormalized_score is an archived diagnostic preview.
- Neither value is the canonical production score.
- Factor presence is not canonical signal authority coverage.

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
    """Full audit of the SignalEngine inputs for one ticker.

    Audits the archived six-factor baseline, not canonical production authority
    coverage.
    """

    ticker: str
    snapshot_date: date
    entries: tuple[SignalAuditEntry, ...]
    final_score: int         # archived baseline score
    strength: str
    entry_quality: str
    coverage_warning: str | None
    factors_present: int     # archived factor availability
    factors_missing: int
    renormalized_score: int  # archived diagnostic preview: score if missing factors excluded from weight pool
