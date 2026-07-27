"""
Canonical signal evidence input boundary — ADR-041.

Binds one setup/flow evidence group to the exact identity of the source rows
actually consumed to produce it, and to source availability resolved from
that same provenance. This is the single typed contract screen and swing
must both cross before `AssessSignalEvidenceUseCase` scores evidence — it
prevents availability from ever describing a different repository read than
the one that produced the scored evidence.

`SHADOW` availability is observable but must never change score, coverage,
classification, candidate selection, or verdict. HIGH-2 (see ADR-041's
amendment) enforces availability as production-authority coverage — this
changes `signal_authority_coverage` and downstream decision eligibility only.
Directional score arithmetic remains based on attached evidence exactly as
before; it is never affected by availability under either mode.

Layer: Domain (pure value objects, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturnStatus
from src.domain.value_objects.benchmark_symbol import CANONICAL_BENCHMARK_TICKER
from src.domain.value_objects.evidence_source_availability import EvidenceSourceAvailability
from src.domain.value_objects.flow_confirmation_evidence import FlowConfirmationEvidence
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.source_availability import SourceAvailabilityStatus


@dataclass(frozen=True)
class CandleRowIdentity:
    """Identity of one candle row actually consumed for setup evidence."""

    ticker: str
    date: date
    source: str | None


@dataclass(frozen=True)
class BrokerSummaryRowIdentity:
    """Identity of one broker-summary row actually consumed for flow evidence."""

    ticker: str
    date: date
    source: str | None


@dataclass(frozen=True)
class BrokerDailyFlowRowIdentity:
    """Identity of one broker-daily-flow row actually consumed for flow evidence."""

    ticker: str
    date: date
    broker_code: str
    source: str | None


def _duplicate_identities(rows: tuple) -> bool:
    return len(set(rows)) != len(rows)


@dataclass(frozen=True)
class SetupProvenance:
    """Exact rows consumed to produce one ticker's `SetupEvidence`.

    `candle_rows` are the ticker's own candles; `benchmark_candle_rows` are
    the benchmark index's candles (a different instrument by design — see
    `CANONICAL_BENCHMARK_TICKER`), consumed only when benchmark excess return
    was actually computed for this evidence.
    """

    ticker: str
    candle_rows: tuple[CandleRowIdentity, ...]
    benchmark_candle_rows: tuple[CandleRowIdentity, ...] = ()

    def __post_init__(self) -> None:
        for row in self.candle_rows:
            if row.ticker != self.ticker:
                raise ValueError(
                    f"SetupProvenance candle_rows ticker mismatch: "
                    f"provenance ticker={self.ticker!r}, row ticker={row.ticker!r}"
                )
        for row in self.benchmark_candle_rows:
            if row.ticker != CANONICAL_BENCHMARK_TICKER:
                raise ValueError(
                    f"SetupProvenance benchmark_candle_rows must be "
                    f"{CANONICAL_BENCHMARK_TICKER!r}, got {row.ticker!r}"
                )
        if _duplicate_identities(self.candle_rows):
            raise ValueError("SetupProvenance candle_rows contains duplicate row identities")
        if _duplicate_identities(self.benchmark_candle_rows):
            raise ValueError(
                "SetupProvenance benchmark_candle_rows contains duplicate row identities"
            )


@dataclass(frozen=True)
class FlowProvenance:
    """Exact rows consumed to produce one ticker's `FlowConfirmationEvidence`."""

    ticker: str
    broker_summary_rows: tuple[BrokerSummaryRowIdentity, ...]
    broker_daily_flow_rows: tuple[BrokerDailyFlowRowIdentity, ...]
    has_bandar_contributor: bool = False

    def __post_init__(self) -> None:
        for row in self.broker_summary_rows:
            if row.ticker != self.ticker:
                raise ValueError(
                    f"FlowProvenance broker_summary_rows ticker mismatch: "
                    f"provenance ticker={self.ticker!r}, row ticker={row.ticker!r}"
                )
        for row in self.broker_daily_flow_rows:
            if row.ticker != self.ticker:
                raise ValueError(
                    f"FlowProvenance broker_daily_flow_rows ticker mismatch: "
                    f"provenance ticker={self.ticker!r}, row ticker={row.ticker!r}"
                )
        if _duplicate_identities(self.broker_summary_rows):
            raise ValueError("FlowProvenance broker_summary_rows contains duplicate row identities")
        if _duplicate_identities(self.broker_daily_flow_rows):
            raise ValueError(
                "FlowProvenance broker_daily_flow_rows contains duplicate row identities"
            )


def _max_date(rows: tuple, key) -> date | None:
    dates = [key(row) for row in rows]
    return max(dates) if dates else None


def _require_assessment(availability: EvidenceSourceAvailability, source_family: str) -> "object":
    for assessment in availability.assessments:
        if assessment.source_family == source_family:
            return assessment
    raise ValueError(
        f"EvidenceSourceAvailability for group {availability.evidence_group!r} is "
        f"missing a required {source_family!r} assessment"
    )


def _benchmark_excess_return_available(excess_return) -> bool:
    return (
        excess_return is not None and excess_return.status == BenchmarkExcessReturnStatus.AVAILABLE
    )


def _validate_observed_through(assessment, expected: date | None, source_family: str) -> None:
    if assessment.observed_through != expected:
        raise ValueError(
            f"{source_family!r} assessment observed_through={assessment.observed_through!r} "
            f"does not match max consumed row date={expected!r}"
        )


def _validate_no_rows_after_snapshot(
    rows: tuple,
    *,
    snapshot_date: date,
    provenance_field: str,
) -> None:
    future_dates = tuple(row.date for row in rows if row.date > snapshot_date)
    if not future_dates:
        return

    latest_future_date = max(future_dates)
    raise ValueError(
        f"{provenance_field} contains row dated {latest_future_date} "
        f"after evidence.snapshot_date={snapshot_date}"
    )


def _validate_empty_row_group_is_unknown(assessment, has_rows: bool, source_family: str) -> None:
    if has_rows:
        return
    if assessment.status != SourceAvailabilityStatus.UNKNOWN or assessment.is_authoritative:
        raise ValueError(
            f"{source_family!r} assessment describes no consumed rows but is not "
            f"explicit UNKNOWN/non-authoritative "
            f"(status={assessment.status!r}, is_authoritative={assessment.is_authoritative!r})"
        )


@dataclass(frozen=True)
class SetupEvidenceGroupInput:
    """Immutable setup evidence + the exact provenance/availability that authorize it."""

    evidence: SetupEvidence
    provenance: SetupProvenance
    availability: EvidenceSourceAvailability

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, SetupEvidence):
            raise ValueError(
                f"SetupEvidenceGroupInput.evidence must be a SetupEvidence, "
                f"got {type(self.evidence)!r}"
            )
        if self.evidence.ticker != self.provenance.ticker:
            raise ValueError(
                f"SetupEvidenceGroupInput ticker mismatch: "
                f"evidence.ticker={self.evidence.ticker!r}, "
                f"provenance.ticker={self.provenance.ticker!r}"
            )
        _validate_no_rows_after_snapshot(
            self.provenance.candle_rows,
            snapshot_date=self.evidence.snapshot_date,
            provenance_field="SetupEvidenceGroupInput.provenance.candle_rows",
        )
        _validate_no_rows_after_snapshot(
            self.provenance.benchmark_candle_rows,
            snapshot_date=self.evidence.snapshot_date,
            provenance_field="SetupEvidenceGroupInput.provenance.benchmark_candle_rows",
        )
        if self.availability.evidence_group != "setup":
            raise ValueError(
                f"SetupEvidenceGroupInput availability.evidence_group must be "
                f"'setup', got {self.availability.evidence_group!r}"
            )
        candles_assessment = _require_assessment(self.availability, "candles")
        _validate_observed_through(
            candles_assessment,
            _max_date(self.provenance.candle_rows, lambda r: r.date),
            "candles",
        )
        _validate_empty_row_group_is_unknown(
            candles_assessment, bool(self.provenance.candle_rows), "candles"
        )
        if _benchmark_excess_return_available(
            self.evidence.benchmark_excess_return_5_session
        ) or _benchmark_excess_return_available(self.evidence.benchmark_excess_return_20_session):
            if not self.provenance.benchmark_candle_rows:
                raise ValueError(
                    "SetupEvidenceGroupInput has an AVAILABLE benchmark excess-return "
                    "sub-signal but provenance.benchmark_candle_rows is empty"
                )


@dataclass(frozen=True)
class FlowEvidenceGroupInput:
    """Immutable flow evidence + the exact provenance/availability that authorize it."""

    evidence: FlowConfirmationEvidence
    provenance: FlowProvenance
    availability: EvidenceSourceAvailability

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, FlowConfirmationEvidence):
            raise ValueError(
                f"FlowEvidenceGroupInput.evidence must be a FlowConfirmationEvidence, "
                f"got {type(self.evidence)!r}"
            )
        if self.evidence.ticker != self.provenance.ticker:
            raise ValueError(
                f"FlowEvidenceGroupInput ticker mismatch: "
                f"evidence.ticker={self.evidence.ticker!r}, "
                f"provenance.ticker={self.provenance.ticker!r}"
            )
        _validate_no_rows_after_snapshot(
            self.provenance.broker_summary_rows,
            snapshot_date=self.evidence.snapshot_date,
            provenance_field="FlowEvidenceGroupInput.provenance.broker_summary_rows",
        )
        _validate_no_rows_after_snapshot(
            self.provenance.broker_daily_flow_rows,
            snapshot_date=self.evidence.snapshot_date,
            provenance_field="FlowEvidenceGroupInput.provenance.broker_daily_flow_rows",
        )
        if self.availability.evidence_group != "flow":
            raise ValueError(
                f"FlowEvidenceGroupInput availability.evidence_group must be "
                f"'flow', got {self.availability.evidence_group!r}"
            )
        summaries_assessment = _require_assessment(self.availability, "broker_summaries")
        _validate_observed_through(
            summaries_assessment,
            _max_date(self.provenance.broker_summary_rows, lambda r: r.date),
            "broker_summaries",
        )
        _validate_empty_row_group_is_unknown(
            summaries_assessment, bool(self.provenance.broker_summary_rows), "broker_summaries"
        )
        daily_flow_assessment = _require_assessment(self.availability, "broker_daily_flow")
        _validate_observed_through(
            daily_flow_assessment,
            _max_date(self.provenance.broker_daily_flow_rows, lambda r: r.date),
            "broker_daily_flow",
        )
        _validate_empty_row_group_is_unknown(
            daily_flow_assessment,
            bool(self.provenance.broker_daily_flow_rows),
            "broker_daily_flow",
        )
        if self.provenance.has_bandar_contributor:
            has_bandar_assessment = any(
                a.source_family == "bandar_detector" for a in self.availability.assessments
            )
            if not has_bandar_assessment and "bandar_detector" not in (
                self.availability.unassessed_contributors
            ):
                raise ValueError(
                    "FlowEvidenceGroupInput provenance.has_bandar_contributor is True but "
                    "availability has no 'bandar_detector' assessment and does not list "
                    "'bandar_detector' in unassessed_contributors — this would let "
                    "all_authoritative=True hide a real, unassessed contributor"
                )


@dataclass(frozen=True)
class CanonicalSignalEvidenceInput:
    """One canonical pre-score boundary shared by screen and swing (ADR-041).

    A missing evidence group is represented only by `setup is None` /
    `flow is None` — never by an empty-but-present group.
    """

    setup: SetupEvidenceGroupInput | None
    flow: FlowEvidenceGroupInput | None
