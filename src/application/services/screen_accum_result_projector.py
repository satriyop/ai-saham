"""
Projects raw accumulation-screen results into the exact candidate/row set
consumed by both table and JSON renderers.

Owns vwap_only / squeeze_only / top / sort_by filtering and multi-window
pattern classification so table and JSON adapters never re-derive their own
candidate set — they render whatever this module decided.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.application.services.accumulation_multi_window_pattern import (
    classify_multi_window_pattern,
)
from src.application.services.broker_quality import BrokerQualitySnapshot
from src.application.services.data_freshness_service import compute_data_freshness


class ScreenAccumProjectionError(ValueError):
    """Raised when screen accum projection inputs are invalid or unsupported."""


# ---------------------------------------------------------------------------
# Single-window projection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SingleScreenAppliedFilters:
    vwap_only: bool
    squeeze_only: bool
    min_streak: int
    top: int


@dataclass(frozen=True)
class ScreenAccumSingleProjection:
    candidates: list[AccumulationCandidate]
    applied_filters: SingleScreenAppliedFilters
    raw_candidate_count: int
    projected_candidate_count: int
    window_days: int
    screened_at: date
    data_as_of: dict[str, str | None]

    def to_dict(self) -> dict:
        return {
            "applied_filters": {
                "vwap_only": self.applied_filters.vwap_only,
                "squeeze_only": self.applied_filters.squeeze_only,
                "min_streak": self.applied_filters.min_streak,
                "top": self.applied_filters.top,
            },
            "counts_before_filter": self.raw_candidate_count,
            "counts_after_filter": self.projected_candidate_count,
            "data_as_of": self.data_as_of,
        }


def project_single_screen_result(
    response: AccumulationScreenResponse,
    *,
    vwap_only: bool,
    squeeze_only: bool,
    top: int,
    min_streak: int,
    coiled_spring_bb_pctile: float,
) -> ScreenAccumSingleProjection:
    """Apply min_streak/vwap_only/squeeze_only/top exactly once, in the order
    the table has always applied them. `raw_candidate_count` reflects the
    screen response before any of these filters."""
    candidates = response.candidates
    raw_count = len(candidates)

    if min_streak > 0:
        candidates = [c for c in candidates if c.consecutive_streak >= min_streak]
    if vwap_only:
        candidates = [c for c in candidates if c.vwap_discount_pct and c.vwap_discount_pct > 0]
    if squeeze_only:
        candidates = [
            c
            for c in candidates
            if c.bb_width_pctile is not None and c.bb_width_pctile <= coiled_spring_bb_pctile
        ]

    candidates = candidates[:top]

    for c in candidates:
        coverage = (
            c.signal_assessment.assessment.coverage_score if c.signal_assessment else None
        )
        c.freshness = compute_data_freshness(
            candle_as_of=c.latest_candle_date,
            broker_as_of=c.latest_broker_date,
            screen_date=response.screened_at,
            signal_evidence_coverage=coverage,
        )

    latest_candle = max(
        (c.latest_candle_date for c in candidates if c.latest_candle_date), default=None
    )
    latest_broker = max(
        (c.latest_broker_date for c in candidates if c.latest_broker_date), default=None
    )

    return ScreenAccumSingleProjection(
        candidates=candidates,
        applied_filters=SingleScreenAppliedFilters(
            vwap_only=vwap_only,
            squeeze_only=squeeze_only,
            min_streak=min_streak,
            top=top,
        ),
        raw_candidate_count=raw_count,
        projected_candidate_count=len(candidates),
        window_days=response.window_days,
        screened_at=response.screened_at,
        data_as_of={
            "latest_candle_date": latest_candle.isoformat() if latest_candle else None,
            "latest_broker_date": latest_broker.isoformat() if latest_broker else None,
        },
    )


# ---------------------------------------------------------------------------
# Multi-window projection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MultiScreenAppliedFilters:
    squeeze_only: bool
    top: int
    sort_by: str


@dataclass(frozen=True)
class ScreenAccumMultiRow:
    ticker: str
    candidates_by_window: dict[int, AccumulationCandidate | None]
    pattern: str
    trend: str
    broker_quality: BrokerQualitySnapshot | None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "windows": {
                f"{w}_sessions": (c.to_dict() if c is not None else None)
                for w, c in self.candidates_by_window.items()
            },
            "pattern": self.pattern,
            "trend": self.trend,
            "broker_quality": self.broker_quality.to_dict() if self.broker_quality else None,
        }


@dataclass(frozen=True)
class ScreenAccumMultiProjection:
    rows: list[ScreenAccumMultiRow]
    applied_filters: MultiScreenAppliedFilters
    requested_windows: list[int]
    resolved_windows: list[int]
    raw_ticker_count: int
    projected_row_count: int
    screened_at: date | None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "applied_filters": {
                "squeeze_only": self.applied_filters.squeeze_only,
                "top": self.applied_filters.top,
                "sort_by": self.applied_filters.sort_by,
            },
            "requested_windows": self.requested_windows,
            "resolved_windows": self.resolved_windows,
            "counts_before_filter": self.raw_ticker_count,
            "counts_after_filter": self.projected_row_count,
        }


def _normalize_sort_by_window(sort_by: str) -> int | None:
    """Parse a window-label sort_by ("7s", "30d", ...) to its integer window.
    Returns None if sort_by is not a window-label form at all (e.g. "avg")."""
    if not sort_by:
        return None
    stripped = sort_by.rstrip("ds")
    if not stripped or not stripped.isdigit():
        return None
    return int(stripped)


def validate_multi_window_request(windows: list[int], sort_by: str) -> None:
    """Fail explicitly on duplicate/empty windows and invalid sort_by values."""
    if not windows:
        raise ScreenAccumProjectionError("At least one window is required for --multi.")

    if len(windows) != len(set(windows)):
        dupes = sorted({w for w in windows if windows.count(w) > 1})
        raise ScreenAccumProjectionError(
            f"Duplicate windows requested: {', '.join(str(w) for w in dupes)}."
        )

    if sort_by in ("avg", "max"):
        return

    window = _normalize_sort_by_window(sort_by)
    valid_labels = ", ".join(f"{w}s" for w in windows)
    if window is None:
        raise ScreenAccumProjectionError(
            f"Invalid --sort-by value {sort_by!r}. Must be avg, max, or one of: {valid_labels}."
        )
    if window not in windows:
        raise ScreenAccumProjectionError(
            f"--sort-by window {sort_by!r} is not in the resolved windows ({valid_labels})."
        )


def project_multi_screen_result(
    multi_results: dict[int, AccumulationScreenResponse],
    *,
    broker_quality: dict[str, BrokerQualitySnapshot] | None,
    windows: list[int],
    top: int,
    sort_by: str,
    squeeze_only: bool,
    coiled_spring_min_foreign_flow_score: float,
    coiled_spring_bb_pctile: float,
) -> ScreenAccumMultiProjection:
    validate_multi_window_request(windows, sort_by)

    resolved_windows = sorted(multi_results.keys())
    broker_quality = broker_quality or {}

    by_ticker: dict[str, dict[int, AccumulationCandidate | None]] = {}
    for w, resp in multi_results.items():
        for c in resp.candidates:
            by_ticker.setdefault(c.ticker, {})[w] = c

    raw_ticker_count = len(by_ticker)

    if squeeze_only:
        by_ticker = {
            tk: pw
            for tk, pw in by_ticker.items()
            if any(
                c.bb_width_pctile is not None and c.bb_width_pctile <= coiled_spring_bb_pctile
                for c in pw.values()
            )
        }

    def sort_key(item: tuple) -> float:
        pw = item[1]
        scores = [c.foreign_flow_score for c in pw.values()]
        if not scores:
            return 0.0
        if sort_by == "avg":
            return sum(scores) / len(scores)
        if sort_by == "max":
            return max(scores)
        window = _normalize_sort_by_window(sort_by)
        c = pw.get(window) if window is not None else None
        return c.foreign_flow_score if c else 0.0

    sorted_items = sorted(by_ticker.items(), key=sort_key, reverse=True)[:top]

    rows = [
        ScreenAccumMultiRow(
            ticker=ticker,
            candidates_by_window=pw,
            pattern=classify_multi_window_pattern(
                resolved_windows,
                pw,
                coiled_spring_min_foreign_flow_score,
                coiled_spring_bb_pctile,
            ),
            trend=next((c.trend for w in resolved_windows for c in [pw.get(w)] if c), "—"),
            broker_quality=broker_quality.get(ticker),
        )
        for ticker, pw in sorted_items
    ]

    screened_at = next(iter(multi_results.values())).screened_at if multi_results else None

    return ScreenAccumMultiProjection(
        rows=rows,
        applied_filters=MultiScreenAppliedFilters(
            squeeze_only=squeeze_only,
            top=top,
            sort_by=sort_by,
        ),
        requested_windows=windows,
        resolved_windows=resolved_windows,
        raw_ticker_count=raw_ticker_count,
        projected_row_count=len(rows),
        screened_at=screened_at,
    )
