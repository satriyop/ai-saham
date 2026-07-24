"""Policy-free projection presenter (legacy; Screen workspace uses ScreenPresenter).

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass

from src.adapters.tui.controllers.accumulation_controller import (
    AccumulationControllerPayload,
    AccumulationProjection,
)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


@dataclass(frozen=True)
class AccumulationRowView:
    source: object
    ticker: str
    canonical_window: int
    signal_score: float | None
    signal_coverage: float | None
    risk: str | None
    setup_phase: str | None
    data_state: str | None
    next_action: str | None
    warning: str | None


@dataclass(frozen=True)
class AccumulationViewModel:
    source: AccumulationProjection
    multi: bool
    rows: tuple[AccumulationRowView, ...]
    metadata: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]


class AccumulationPresenter:
    def present(self, payload: AccumulationControllerPayload) -> AccumulationViewModel:
        projection = payload.projection
        if payload.multi:
            rows = tuple(self._multi_row(row) for row in projection.rows)
            metadata = (
                ("Mode", "MULTI"),
                ("Canonical window", f"{projection.canonical_window} sessions"),
                ("Requested windows", ", ".join(map(str, projection.requested_windows))),
                ("Counts", f"{projection.projected_row_count}/{projection.raw_ticker_count}"),
                ("Sort", projection.applied_filters.sort_by),
            )
            warnings = tuple(payload.result.warnings) + tuple(projection.warnings)
        else:
            rows = tuple(
                self._single_row(candidate, projection.window_days)
                for candidate in projection.candidates
            )
            metadata = (
                ("Mode", "SINGLE"),
                ("Canonical window", f"{projection.window_days} sessions"),
                (
                    "Counts",
                    f"{projection.projected_candidate_count}/{projection.raw_candidate_count}",
                ),
                ("Sort", projection.applied_filters.sort_by),
                ("Candle as of", projection.data_as_of.get("latest_candle_date") or "—"),
                ("Broker as of", projection.data_as_of.get("latest_broker_date") or "—"),
            )
            warnings = tuple(payload.result.warnings)
        return AccumulationViewModel(projection, payload.multi, rows, metadata, warnings)

    @staticmethod
    def _single_row(candidate, window: int) -> AccumulationRowView:
        signal = candidate.signal_assessment
        risk = candidate.risk_assessment
        phase = candidate.setup_phase
        freshness = candidate.freshness
        trade_setup = candidate.trade_setup
        return AccumulationRowView(
            source=candidate,
            ticker=candidate.ticker,
            canonical_window=window,
            signal_score=signal.assessment.score if signal else None,
            signal_coverage=(signal.assessment.signal_authority_coverage if signal else None),
            risk=risk.risk_level_name if risk else None,
            setup_phase=_enum_value(phase.current_phase) if phase else None,
            data_state=_enum_value(freshness.alignment_state) if freshness else None,
            next_action=_enum_value(trade_setup.action) if trade_setup else None,
            warning=signal.coverage_warning if signal else None,
        )

    @staticmethod
    def _multi_row(row) -> AccumulationRowView:
        warning = None
        candidate = row.canonical_candidate
        if candidate is not None and candidate.signal_assessment is not None:
            warning = candidate.signal_assessment.coverage_warning
        return AccumulationRowView(
            source=row,
            ticker=row.ticker,
            canonical_window=row.canonical_window,
            signal_score=row.signal_score,
            signal_coverage=row.signal_authority_coverage,
            risk=row.risk_status,
            setup_phase=row.setup_phase,
            data_state=row.data_status,
            next_action=row.next_action,
            warning=warning,
        )
