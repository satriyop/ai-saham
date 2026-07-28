"""DTOs for post-open assessment of an immutable NCP pre-open plan.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from src.domain.value_objects.pre_open_post_open_assessment import PreOpenPostOpenAssessment


class AssessPreOpenStatus(str, Enum):
    """Overall status of a post-open analyze run."""

    OK = "OK"
    PARTIAL = "PARTIAL"  # some tickers lacked opening price
    UNAVAILABLE_OPENING = "UNAVAILABLE_OPENING"  # no usable opening snapshot for any row


@dataclass(frozen=True)
class AssessPreOpenRequest:
    """Select immutable observation(s) + optional opening track snapshot."""

    session_date: date | None = None
    observation_id: str | None = None
    opening_snapshot_id: str | None = None


@dataclass(frozen=True)
class AssessPreOpenLine:
    """One ticker's frozen pre-open state + post-open confirmation."""

    observation_id: str
    opening_snapshot_id: str | None
    ticker: str
    pre_open: Mapping[str, Any]
    confirmation: PreOpenPostOpenAssessment
    price_provenance: Mapping[str, Any]
    cutoff_at: datetime
    compatibility_id: str
    contract_id: str


@dataclass(frozen=True)
class AssessPreOpenResult:
    """Read-only post-open assessment result (no journal write)."""

    session_date: date
    status: AssessPreOpenStatus
    market_regime: str | None
    max_stop_pct: Decimal
    lines: tuple[AssessPreOpenLine, ...]
    warnings: tuple[str, ...] = ()
    policy_identity: Mapping[str, Any] = field(default_factory=dict)

    @property
    def observation_ids(self) -> tuple[str, ...]:
        return tuple(line.observation_id for line in self.lines)

    @property
    def opening_snapshot_ids(self) -> tuple[str, ...]:
        return tuple(
            line.opening_snapshot_id for line in self.lines if line.opening_snapshot_id is not None
        )


class AssessPreOpenError(Exception):
    """Base fail-closed error for analyze pre-open selection/lineage."""


class AssessPreOpenNotFoundError(AssessPreOpenError):
    """Observation or required artifact not found."""


class AssessPreOpenContractError(AssessPreOpenError):
    """Wrong purpose/contract or cross-observation snapshot substitution."""


class AssessPreOpenAmbiguityError(AssessPreOpenError):
    """Multiple compatible cohorts without explicit observation_id."""


class AssessPreOpenSnapshotError(AssessPreOpenError):
    """Opening snapshot identity/linkage error (not mere missing open price)."""
