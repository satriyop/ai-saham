"""
DataFreshnessStatus — typed source freshness/alignment for market data.

Replaces the misleading "Fresh: OK" concept, which conflated candle/broker
source-date equality (alignment) with data being current for the active
market session (readiness). The two are orthogonal:

- Alignment: do candle and broker sources report the same as-of date?
- Readiness: is a source's as-of date current given the expected latest
  IDX end-of-day session?

Layer: Domain (pure value object, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class SourceFreshnessState(str, Enum):
    """Readiness of a single source (candle or broker) relative to the
    expected latest EOD trading session."""

    READY = "READY"
    PENDING_EOD = "PENDING_EOD"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class SourceAlignmentState(str, Enum):
    """Agreement between candle and broker source as-of dates."""

    ALIGNED = "ALIGNED"
    LAG = "LAG"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DataFreshnessStatus:
    """Typed freshness/alignment snapshot for one ticker's candle+broker data.

    `sources_aligned` is a convenience bool mirroring
    `alignment_state == SourceAlignmentState.ALIGNED`; kept as an explicit
    field so JSON consumers do not need to parse the enum string.
    """

    candle_as_of: date | None
    broker_as_of: date | None
    expected_latest_eod: date | None
    candle_state: SourceFreshnessState
    broker_state: SourceFreshnessState
    alignment_state: SourceAlignmentState
    sources_aligned: bool
    signal_evidence_coverage: float | None

    def to_dict(self) -> dict:
        return {
            "candle_as_of": self.candle_as_of.isoformat() if self.candle_as_of else None,
            "broker_as_of": self.broker_as_of.isoformat() if self.broker_as_of else None,
            "expected_latest_eod": (
                self.expected_latest_eod.isoformat() if self.expected_latest_eod else None
            ),
            "candle_state": self.candle_state.value,
            "broker_state": self.broker_state.value,
            "alignment_state": self.alignment_state.value,
            "sources_aligned": self.sources_aligned,
            "signal_evidence_coverage": self.signal_evidence_coverage,
        }
