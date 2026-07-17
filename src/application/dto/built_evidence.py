"""
Typed build results pairing evidence with its exact consumed-row provenance
(ADR-041). Evidence and provenance must be produced together and never
reconstructed or overwritten separately — these types exist so builders
cannot return one without the other.

Layer: Application (DTO)
Depends on: domain value objects only
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturnStatus
from src.domain.value_objects.canonical_signal_evidence_input import (
    FlowProvenance,
    SetupProvenance,
)
from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
from src.domain.value_objects.setup_evidence import SetupEvidence


def _benchmark_excess_return_available(excess_return) -> bool:
    return (
        excess_return is not None
        and excess_return.status == BenchmarkExcessReturnStatus.AVAILABLE
    )


@dataclass(frozen=True)
class BuiltSetupEvidence:
    """A `SetupEvidence` and the exact rows consumed to produce it."""

    evidence: SetupEvidence
    provenance: SetupProvenance

    def __post_init__(self) -> None:
        if self.evidence.ticker != self.provenance.ticker:
            raise ValueError(
                f"BuiltSetupEvidence ticker mismatch: "
                f"evidence.ticker={self.evidence.ticker!r}, "
                f"provenance.ticker={self.provenance.ticker!r}"
            )
        for row in self.provenance.candle_rows:
            if row.date > self.evidence.snapshot_date:
                raise ValueError(
                    f"BuiltSetupEvidence has a ticker candle dated {row.date!r} "
                    f"after evidence.snapshot_date={self.evidence.snapshot_date!r}"
                )
        for row in self.provenance.benchmark_candle_rows:
            if row.date > self.evidence.snapshot_date:
                raise ValueError(
                    f"BuiltSetupEvidence has a benchmark candle dated {row.date!r} "
                    f"after evidence.snapshot_date={self.evidence.snapshot_date!r}"
                )
        if (
            _benchmark_excess_return_available(self.evidence.benchmark_excess_return_5_session)
            or _benchmark_excess_return_available(
                self.evidence.benchmark_excess_return_20_session
            )
        ) and not self.provenance.benchmark_candle_rows:
            raise ValueError(
                "BuiltSetupEvidence has an AVAILABLE benchmark excess-return "
                "sub-signal but provenance.benchmark_candle_rows is empty"
            )


@dataclass(frozen=True)
class BuiltFlowEvidence:
    """A `FlowConfirmationEvidence` and the exact rows consumed to produce it."""

    evidence: FlowConfirmationEvidence
    provenance: FlowProvenance

    def __post_init__(self) -> None:
        if self.evidence.ticker != self.provenance.ticker:
            raise ValueError(
                f"BuiltFlowEvidence ticker mismatch: "
                f"evidence.ticker={self.evidence.ticker!r}, "
                f"provenance.ticker={self.provenance.ticker!r}"
            )
        for row in self.provenance.broker_summary_rows:
            if row.date > self.evidence.snapshot_date:
                raise ValueError(
                    f"BuiltFlowEvidence has a broker summary dated {row.date!r} "
                    f"after evidence.snapshot_date={self.evidence.snapshot_date!r}"
                )
        for row in self.provenance.broker_daily_flow_rows:
            if row.date > self.evidence.snapshot_date:
                raise ValueError(
                    f"BuiltFlowEvidence has a broker daily-flow row dated {row.date!r} "
                    f"after evidence.snapshot_date={self.evidence.snapshot_date!r}"
                )
