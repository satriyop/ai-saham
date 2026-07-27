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


class AnalyzePreOpenStatus(str, Enum):
    """Overall status of a post-open analyze run."""

    OK = "OK"
    PARTIAL = "PARTIAL"  # some tickers lacked opening price
    UNAVAILABLE_OPENING = "UNAVAILABLE_OPENING"  # no usable opening snapshot for any row


@dataclass(frozen=True)
class AnalyzePreOpenRequest:
    """Select immutable observation(s) + optional opening track snapshot."""

    session_date: date | None = None
    observation_id: str | None = None
    opening_snapshot_id: str | None = None


@dataclass(frozen=True)
class AnalyzePreOpenLine:
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
class AnalyzePreOpenResult:
    """Read-only post-open assessment result (no journal write)."""

    session_date: date
    status: AnalyzePreOpenStatus
    market_regime: str | None
    max_stop_pct: Decimal
    lines: tuple[AnalyzePreOpenLine, ...]
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


class AnalyzePreOpenError(Exception):
    """Base fail-closed error for analyze pre-open selection/lineage."""


class AnalyzePreOpenNotFoundError(AnalyzePreOpenError):
    """Observation or required artifact not found."""


class AnalyzePreOpenContractError(AnalyzePreOpenError):
    """Wrong purpose/contract or cross-observation snapshot substitution."""


class AnalyzePreOpenAmbiguityError(AnalyzePreOpenError):
    """Multiple compatible cohorts without explicit observation_id."""


class AnalyzePreOpenSnapshotError(AnalyzePreOpenError):
    """Opening snapshot identity/linkage error (not mere missing open price)."""
