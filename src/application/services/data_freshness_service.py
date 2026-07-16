"""
Freshness computation from the canonical effective IDX session.

Computes a `DataFreshnessStatus` for a ticker's candle/broker source dates
against the expected latest IDX end-of-day session, taken from an
`EffectiveMarketSession` resolved once per run by
`EffectiveMarketSessionResolver` (see `effective_market_session_resolver.py`).
This module owns no wall-clock/weekday arithmetic itself — callers resolve
the session once and pass the same `EffectiveMarketSession` into every
`compute_data_freshness` call for that run.

Layer: Application
"""

from __future__ import annotations

from datetime import date

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.value_objects.data_freshness_status import (
    DataFreshnessStatus,
    SourceAlignmentState,
    SourceFreshnessState,
)


def _classify_source_state(
    source_date: date | None,
    expected_latest_eod: date | None,
    eod_pending: bool,
) -> SourceFreshnessState:
    if source_date is None:
        return SourceFreshnessState.MISSING
    if expected_latest_eod is None:
        return SourceFreshnessState.UNKNOWN
    if source_date == expected_latest_eod:
        return SourceFreshnessState.PENDING_EOD if eod_pending else SourceFreshnessState.READY
    if source_date < expected_latest_eod:
        return SourceFreshnessState.STALE
    return SourceFreshnessState.READY  # newer than expected (clock skew) — at least current


def _classify_alignment(
    candle_as_of: date | None, broker_as_of: date | None
) -> SourceAlignmentState:
    if candle_as_of is None or broker_as_of is None:
        return SourceAlignmentState.MISSING
    if candle_as_of == broker_as_of:
        return SourceAlignmentState.ALIGNED
    return SourceAlignmentState.LAG


def compute_data_freshness(
    *,
    candle_as_of: date | None,
    broker_as_of: date | None,
    effective_session: EffectiveMarketSession,
    signal_evidence_coverage: float | None = None,
) -> DataFreshnessStatus:
    """Compute typed freshness/alignment for one ticker's candle+broker data.

    `effective_session` is the canonical resolved IDX session for the run
    this freshness check belongs to (`EffectiveMarketSessionResolver.resolve`
    output). Its `latest_completed_session` becomes `expected_latest_eod` and
    its `is_eod_pending` drives the READY-vs-PENDING_EOD distinction below.
    """
    expected_latest_eod = effective_session.latest_completed_session
    eod_pending = effective_session.is_eod_pending

    return DataFreshnessStatus(
        candle_as_of=candle_as_of,
        broker_as_of=broker_as_of,
        expected_latest_eod=expected_latest_eod,
        candle_state=_classify_source_state(candle_as_of, expected_latest_eod, eod_pending),
        broker_state=_classify_source_state(broker_as_of, expected_latest_eod, eod_pending),
        alignment_state=_classify_alignment(candle_as_of, broker_as_of),
        sources_aligned=(
            candle_as_of is not None
            and broker_as_of is not None
            and candle_as_of == broker_as_of
        ),
        signal_evidence_coverage=signal_evidence_coverage,
    )
