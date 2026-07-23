"""Immutable, policy-free projection of ``DailyBriefingResponse`` for Textual.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse
from src.application.use_case.refresh_daily_workspace_use_case import (
    RefreshDailyWorkspaceResult,
)


def _date_text(value) -> str | None:
    return value.isoformat() if value is not None else None


@dataclass(frozen=True)
class DailyClockView:
    label: str
    value: str | None


@dataclass(frozen=True)
class DailyFreshnessView:
    ticker: str
    candle_as_of: str | None
    candle_state: str
    broker_as_of: str | None
    broker_state: str
    alignment_state: str


@dataclass(frozen=True)
class DailyReadinessView:
    dataset: str
    status: str
    coverage_count: int
    total_count: int
    required_as_of: str | None
    reason: str | None


@dataclass(frozen=True)
class DailyRegimeFactorView:
    name: str
    value: float | None
    score: float | None
    label: str
    rationale: str


@dataclass(frozen=True)
class DailyRegimeView:
    regime: str
    conviction: float
    confidence: float | None
    stability: str | None
    days_in_regime: int | None
    transition_warning: str | None
    staleness_warning: str | None
    coverage_warning: str | None
    factors: tuple[DailyRegimeFactorView, ...]


@dataclass(frozen=True)
class DailyOpeningView:
    ticker: str
    opening_setup: str
    iev: int | None
    iep: int | None
    trend: str | None
    accum_score: float | None


@dataclass(frozen=True)
class DailyAccumulationSummaryView:
    checked: int
    data_ready: int
    flow_candidates: int
    enter_count: int
    watch_count: int
    blocked_count: int
    unclassified_count: int


@dataclass(frozen=True)
class DailyAccumulationCandidateView:
    ticker: str
    accum_score: float
    setup_phase: str | None
    signal_score: int | None
    signal_authority_coverage: float | None
    risk_status: str
    action: str | None


@dataclass(frozen=True)
class DailySetupLensCellView:
    setup_name: str
    action: str | None
    signal_score: int | None
    setup_match: str
    entry_authority: bool | None
    capped_reason: str | None
    warning: str | None


@dataclass(frozen=True)
class DailySetupLensRowView:
    ticker: str
    base_action: str | None
    cells: tuple[DailySetupLensCellView, ...]


@dataclass(frozen=True)
class DailyViewModel:
    source: DailyBriefingResponse
    clocks: tuple[DailyClockView, DailyClockView, DailyClockView]
    is_historical: bool
    universe: str
    universe_count: int
    stale_count: int
    overall_authority: str
    freshness: tuple[DailyFreshnessView, ...]
    readiness: tuple[DailyReadinessView, ...]
    regime: DailyRegimeView | None
    opening_candidates: tuple[DailyOpeningView, ...]
    market_wide_opening_observations: tuple[DailyOpeningView, ...]
    accumulation_summary: DailyAccumulationSummaryView | None
    accumulation_candidates: tuple[DailyAccumulationCandidateView, ...]
    setup_lens_rows: tuple[DailySetupLensRowView, ...]
    setup_lens_warnings: tuple[str, ...]
    warnings: tuple[str, ...]


class DailyPresenter:
    """Copy canonical Daily values into immutable display-only rows."""

    def present(
        self, payload: DailyBriefingResponse | RefreshDailyWorkspaceResult
    ) -> DailyViewModel:
        if isinstance(payload, RefreshDailyWorkspaceResult):
            response = payload.briefing
            extra_warnings = payload.warnings
        else:
            response = payload
            extra_warnings = ()

        regime = self._regime(response)
        suppress_rankings = response.overall_authority == "NOT_READY"
        setup_result = response.setup_lens_impact

        return DailyViewModel(
            source=response,
            clocks=(
                DailyClockView("Live session", response.live_session_date.isoformat()),
                DailyClockView(
                    "Latest completed EOD",
                    _date_text(response.latest_completed_eod_date),
                ),
                DailyClockView(
                    "Opening snapshot",
                    _date_text(response.opening_snapshot_date),
                ),
            ),
            is_historical=response.is_historical,
            universe=response.universe,
            universe_count=response.universe_count,
            stale_count=response.stale_count,
            overall_authority=response.overall_authority,
            freshness=tuple(
                DailyFreshnessView(
                    ticker=item.ticker,
                    candle_as_of=_date_text(item.freshness.candle_as_of),
                    candle_state=item.freshness.candle_state.value,
                    broker_as_of=_date_text(item.freshness.broker_as_of),
                    broker_state=item.freshness.broker_state.value,
                    alignment_state=item.freshness.alignment_state.value,
                )
                for item in response.data_freshness
            ),
            readiness=tuple(
                DailyReadinessView(
                    dataset=item.dataset,
                    status=item.status,
                    coverage_count=item.coverage_count,
                    total_count=item.total_count,
                    required_as_of=_date_text(item.required_as_of),
                    reason=item.reason,
                )
                for item in response.readiness_items
            ),
            regime=regime,
            opening_candidates=tuple(
                self._opening(candidate) for candidate in response.opening_candidates
            ),
            market_wide_opening_observations=tuple(
                self._opening(candidate) for candidate in response.market_wide_opening_observations
            ),
            accumulation_summary=self._accumulation_summary(response),
            accumulation_candidates=(
                ()
                if suppress_rankings
                else tuple(
                    DailyAccumulationCandidateView(
                        ticker=candidate.ticker,
                        accum_score=candidate.accum_score,
                        setup_phase=candidate.setup_phase,
                        signal_score=candidate.signal_score,
                        signal_authority_coverage=(candidate.signal_authority_coverage),
                        risk_status=candidate.risk_status,
                        action=candidate.action,
                    )
                    for candidate in response.daily_accumulation_candidates
                )
            ),
            setup_lens_rows=(
                ()
                if suppress_rankings or setup_result is None
                else tuple(self._setup_row(row) for row in setup_result.rows)
            ),
            setup_lens_warnings=(() if setup_result is None else tuple(setup_result.warnings)),
            warnings=tuple(response.warnings) + tuple(extra_warnings),
        )

    @staticmethod
    def _opening(candidate) -> DailyOpeningView:
        return DailyOpeningView(
            ticker=candidate.ticker,
            opening_setup=candidate.opening_setup,
            iev=candidate.iev,
            iep=candidate.iep,
            trend=candidate.trend,
            accum_score=candidate.accum_score,
        )

    @staticmethod
    def _accumulation_summary(
        response: DailyBriefingResponse,
    ) -> DailyAccumulationSummaryView | None:
        summary = response.accumulation_summary
        if summary is None:
            return None
        return DailyAccumulationSummaryView(
            checked=summary.checked,
            data_ready=summary.data_ready,
            flow_candidates=summary.flow_candidates,
            enter_count=summary.enter_count,
            watch_count=summary.watch_count,
            blocked_count=summary.blocked_count,
            unclassified_count=summary.unclassified_count,
        )

    @staticmethod
    def _setup_row(row) -> DailySetupLensRowView:
        return DailySetupLensRowView(
            ticker=row.ticker,
            base_action=row.base_action,
            cells=tuple(
                DailySetupLensCellView(
                    setup_name=cell.setup_name,
                    action=cell.action,
                    signal_score=cell.signal_score,
                    setup_match=cell.setup_match,
                    entry_authority=cell.entry_authority,
                    capped_reason=cell.capped_reason,
                    warning=cell.warning,
                )
                for cell in row.cells
            ),
        )

    @staticmethod
    def _regime(response: DailyBriefingResponse) -> DailyRegimeView | None:
        regime = response.regime
        if regime is None:
            return None
        return DailyRegimeView(
            regime=regime.regime.value,
            conviction=regime.conviction,
            confidence=regime.regime_confidence,
            stability=regime.regime_stability,
            days_in_regime=regime.days_in_regime,
            transition_warning=regime.transition_warning,
            staleness_warning=regime.staleness_warning,
            coverage_warning=regime.coverage_warning,
            factors=tuple(
                DailyRegimeFactorView(
                    name=factor.name,
                    value=factor.value,
                    score=factor.score,
                    label=factor.label,
                    rationale=factor.rationale,
                )
                for factor in regime.factors
            ),
        )
