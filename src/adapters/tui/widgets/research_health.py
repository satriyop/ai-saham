"""Render-only helpers for Research Corpus Health.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.tui.presenters.research_health_presenter import (
    ResearchHealthViewModel,
)


def _value(value) -> str:
    return "—" if value is None else str(value)


def _yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def render_target(view: ResearchHealthViewModel) -> str:
    target = view.target
    return "\n".join(
        (
            f"Target: {target.raw}",
            f"Diagnostic target: {_yes_no(target.is_diagnostic)}",
            f"Profile: {target.profile}",
            f"Setup family: {target.setup_family}",
            f"Market-cap bucket: {_value(target.market_cap_bucket)}",
            f"Horizon: {target.horizon}",
        )
    )


def render_cohorts(view: ResearchHealthViewModel) -> str:
    available = ", ".join(view.available_cohorts) or "—"
    return "\n".join(
        (
            f"Selected: {_value(view.selected_cohort)}",
            f"Available: {available}",
        )
    )


def render_counts(view: ResearchHealthViewModel) -> str:
    counts = view.counts
    dates = ", ".join(counts.observation_dates) or "—"
    return "\n".join(
        (
            f"Observation dates: {dates}",
            f"Latest observation date: {_value(counts.latest_observation_date)}",
            f"Latest per-ticker observations: {counts.latest_observations}",
            f"Raw latest observations: {counts.raw_latest_observations}",
            f"Target filter: {counts.target_filter_count}",
            f"Raw target filter: {counts.raw_target_filter_count}",
            f"Labels: {counts.label_count}",
            f"Unavailable labels: {counts.unavailable_label_count}",
            f"Target labels: {counts.target_label_count}",
            f"Raw labeled targets: {counts.raw_labeled_target_count}",
            f"Independent labeled targets: {counts.labeled_target_count}",
            f"Unique tickers: {counts.unique_tickers}",
            f"Unique signal sessions: {counts.unique_signal_dates}",
        )
    )


def render_eligibility(view: ResearchHealthViewModel) -> str:
    item = view.eligibility
    return "\n".join(
        (
            f"Split: {item.split}",
            f"IS / OOS: {item.is_count} / {item.oos_count}",
            f"Diagnostic ready: {_yes_no(item.diagnostic_ready)}",
            f"Patch eligible: {_yes_no(item.patch_eligible)}",
            f"Promotion eligible: {_yes_no(item.promotion_eligible)}",
            f"OOS profit factor: {_value(item.oos_profit_factor)}",
            f"OOS average return: {_value(item.oos_average_return)}",
        )
    )


def render_exclusions(view: ResearchHealthViewModel) -> str:
    return "\n".join(f"{name}: {count}" for name, count in view.exclusions)


def render_lines(lines: tuple[str, ...], *, empty: str) -> str:
    return "\n".join(lines) if lines else empty
