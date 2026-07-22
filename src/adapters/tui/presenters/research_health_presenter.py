"""Immutable, policy-free projection of ``SignalReadinessReport``.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.use_case.report_signal_readiness_use_case import (
    SignalReadinessReport,
)


@dataclass(frozen=True)
class ResearchTargetView:
    raw: str
    is_diagnostic: bool
    profile: str
    setup_family: str
    market_cap_bucket: str | None
    horizon: str


@dataclass(frozen=True)
class ResearchCountView:
    observation_dates: tuple[str, ...]
    latest_observation_date: str | None
    latest_observations: int
    raw_latest_observations: int
    target_filter_count: int
    raw_target_filter_count: int
    label_count: int
    unavailable_label_count: int
    target_label_count: int
    raw_labeled_target_count: int
    labeled_target_count: int
    unique_tickers: int
    unique_signal_dates: int


@dataclass(frozen=True)
class ResearchEligibilityView:
    split: str
    is_count: int
    oos_count: int
    diagnostic_ready: bool
    patch_eligible: bool
    promotion_eligible: bool
    oos_profit_factor: float | None
    oos_average_return: float | None


@dataclass(frozen=True)
class ResearchHealthViewModel:
    source: SignalReadinessReport
    target: ResearchTargetView
    selected_cohort: str | None
    available_cohorts: tuple[str, ...]
    counts: ResearchCountView
    exclusions: tuple[tuple[str, int], ...]
    eligibility: ResearchEligibilityView
    notes: tuple[str, ...]
    blockers: tuple[str, ...]


class ResearchHealthPresenter:
    def present(self, report: SignalReadinessReport) -> ResearchHealthViewModel:
        target = report.target
        return ResearchHealthViewModel(
            source=report,
            target=ResearchTargetView(
                raw=target.raw,
                is_diagnostic=target.is_diagnostic,
                profile=target.profile,
                setup_family=target.setup_family,
                market_cap_bucket=target.market_cap_bucket,
                horizon=target.horizon.value,
            ),
            selected_cohort=report.selected_semantic_compatibility_id,
            available_cohorts=tuple(report.available_semantic_compatibility_ids),
            counts=ResearchCountView(
                observation_dates=tuple(day.isoformat() for day in report.observation_dates),
                latest_observation_date=(
                    report.latest_observation_date.isoformat()
                    if report.latest_observation_date
                    else None
                ),
                latest_observations=report.latest_observation_count,
                raw_latest_observations=report.raw_latest_observation_count,
                target_filter_count=report.target_filter_count,
                raw_target_filter_count=report.raw_target_filter_count,
                label_count=report.label_count,
                unavailable_label_count=report.unavailable_label_count,
                target_label_count=report.target_label_count,
                raw_labeled_target_count=report.raw_labeled_target_count,
                labeled_target_count=report.labeled_target_count,
                unique_tickers=report.unique_tickers,
                unique_signal_dates=report.unique_signal_dates,
            ),
            exclusions=tuple(report.exclusions.to_dict().items()),
            eligibility=ResearchEligibilityView(
                split=report.oos_split,
                is_count=report.is_count,
                oos_count=report.oos_count,
                diagnostic_ready=report.diagnostic_ready,
                patch_eligible=report.patch_eligible,
                promotion_eligible=report.promotion_eligible,
                oos_profit_factor=report.oos_profit_factor,
                oos_average_return=report.oos_average_return,
            ),
            notes=tuple(report.notes),
            blockers=tuple(report.blockers),
        )
