"""Immutable presenter mapping Screen candidates, projections, and comparisons for Textual.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.adapters.shared.vwap_depth_display import vwap_depth_label
from src.application.dto.screen_contract import (
    ScreenResultStatus,
    related_actions_for_accum,
    resolve_accum_result_status,
)
from src.application.use_case.compare_screen_watchlist_use_case import (
    CompareScreenWatchlistResult,
)
from src.application.use_case.list_screen_watchlists_use_case import (
    ListScreenWatchlistsResult,
    ScreenWatchlistSummary,
)
from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


@dataclass(frozen=True)
class ScreenCandidateRowView:
    canonical_rank: int
    ticker: str
    accum_score: float
    consecutive_streak: int
    net_buy_ratio: float
    bci_label: str | None
    setup_phase: str | None
    risk_status: str
    action: str | None
    signal_score: int | None
    signal_authority_coverage: float | None
    window_shape_label: str | None = None
    # Soft VWAP triage (display-only; same bands as CLI Disc% badge).
    vwap_discount_pct: float | None = None
    vwap_depth_label: str | None = None
    # Multi-window Accum scores by session window (CLI multi parity).
    window_accum: tuple[tuple[int, float | None], ...] = ()
    pattern: str | None = None


@dataclass(frozen=True)
class ScreenComparisonGroupView:
    heading: str
    symbol: str
    status_class: str
    tickers_or_changes: tuple[str | tuple[str, str], ...]


@dataclass(frozen=True)
class ScreenRelatedActionView:
    verb: str
    label: str
    command: str


@dataclass(frozen=True)
class ScreenViewModel:
    active_tab: str
    universe_label: str
    candidate_rows: tuple[ScreenCandidateRowView, ...]
    watchlist_summaries: tuple[ScreenWatchlistSummary, ...]
    selected_snapshot_entries: tuple[ScreenSnapshotEntry, ...]
    comparison_result: CompareScreenWatchlistResult | None
    warnings: tuple[str, ...]
    result_status: str = ScreenResultStatus.OK.value
    related_actions: tuple[ScreenRelatedActionView, ...] = ()
    # True when payload is multi-window accumulation (CLI --multi).
    is_multi: bool = False
    resolved_windows: tuple[int, ...] = ()


class ScreenPresenter:
    """Format Screen workflow outputs into immutable UI display structures."""

    def present(
        self, payload: Any, *, active_tab: str = "ACCUMULATION", universe_label: str = "lq45"
    ) -> ScreenViewModel:
        return self.present_accumulation(payload, active_tab=active_tab, universe_label=universe_label)

    @staticmethod
    def _vwap_fields(candidate: Any) -> tuple[float | None, str | None]:
        if candidate is None:
            return None, None
        raw = getattr(candidate, "vwap_discount_pct", None)
        if raw is None or not isinstance(raw, (int, float)):
            return None, None
        pct = float(raw)
        return pct, vwap_depth_label(pct)

    @staticmethod
    def _window_accum_pairs(
        by_window: dict[Any, Any] | None,
        resolved_windows: tuple[int, ...] | list[int],
    ) -> tuple[tuple[int, float | None], ...]:
        """Per-window Accum scores (None = no candidate in that window)."""
        windows = by_window or {}
        pairs: list[tuple[int, float | None]] = []
        for days in resolved_windows:
            cand = windows.get(days)
            if cand is None:
                pairs.append((int(days), None))
            else:
                pairs.append((int(days), float(getattr(cand, "accum_score", 0.0) or 0.0)))
        return tuple(pairs)

    @staticmethod
    def _multi_window_shape_label(
        window_accum: tuple[tuple[int, float | None], ...],
    ) -> str:
        """Compact 7s:… 30s:… label for preview / status."""
        parts: list[str] = []
        for days, score in window_accum:
            if score is None:
                parts.append(f"{days}s:—")
            else:
                parts.append(f"{days}s:{score:.0f}")
        return " ".join(parts)

    @staticmethod
    def _signal_fields(
        candidate: Any, *, row: Any | None = None
    ) -> tuple[int | None, float | None]:
        """Extract SignalEngine total + coverage (ADR-043 signal_score).

        Prefer ``signal_assessment.assessment``; fall back to multi-row
        ``signal_score`` fields. Never confuse with ``accum_score``.
        """
        score: int | float | None = None
        coverage: float | None = None

        sa = getattr(candidate, "signal_assessment", None) if candidate is not None else None
        if sa is not None:
            assessment = getattr(sa, "assessment", None)
            if assessment is not None:
                raw = getattr(assessment, "score", None)
                if isinstance(raw, (int, float)):
                    score = raw
                cov = getattr(assessment, "signal_authority_coverage", None)
                if isinstance(cov, (int, float)):
                    coverage = float(cov)

        if score is None and row is not None:
            raw = getattr(row, "signal_score", None)
            if isinstance(raw, (int, float)):
                score = raw
            cov = getattr(row, "signal_authority_coverage", None)
            if coverage is None and isinstance(cov, (int, float)):
                coverage = float(cov)

        if score is None and candidate is not None:
            raw = getattr(candidate, "signal_score", None)
            if isinstance(raw, (int, float)):
                score = raw

        if coverage is None and candidate is not None:
            cov = getattr(candidate, "signal_authority_coverage", None)
            if isinstance(cov, (int, float)):
                coverage = float(cov)

        score_int = int(score) if isinstance(score, (int, float)) else None
        return score_int, coverage

    def present_accumulation(
        self,
        projection: Any,
        *,
        active_tab: str = "ACCUMULATION",
        universe_label: str = "lq45",
    ) -> ScreenViewModel:
        source = projection
        warnings = tuple(getattr(source, "warnings", ()) or ())
        saved_name = None
        save_result = getattr(source, "save_result", None)
        if save_result is not None:
            saved_name = getattr(save_result, "name", None)

        is_multi = False
        resolved_windows: tuple[int, ...] = ()

        if hasattr(projection, "multi_projection") and projection.multi_projection is not None:
            projection = projection.multi_projection
            is_multi = True
        elif hasattr(projection, "single_projection") and projection.single_projection is not None:
            projection = projection.single_projection

        rows: list[ScreenCandidateRowView] = []
        if hasattr(projection, "rows") or type(projection).__name__ == "ScreenAccumMultiProjection":
            is_multi = True
            raw_windows = getattr(projection, "resolved_windows", None) or (7, 30, 90)
            resolved_windows = tuple(int(w) for w in raw_windows)
            for rank, multi_row in enumerate(projection.rows, 1):
                # canonical_candidate may exist and be None — never treat that as
                # "missing attribute" (getattr default would not run).
                c = getattr(multi_row, "canonical_candidate", None)
                if c is None:
                    c = getattr(multi_row, "candidate", None)

                by_window = getattr(multi_row, "candidates_by_window", None) or {}
                window_accum = self._window_accum_pairs(by_window, resolved_windows)
                shape = self._multi_window_shape_label(window_accum)
                pattern = getattr(multi_row, "pattern", None)

                if c is not None:
                    disc, depth = self._vwap_fields(c)
                    sig_score, sig_cov = self._signal_fields(c, row=multi_row)
                    phase = getattr(c, "setup_phase", None)
                    if not isinstance(phase, str) and phase is not None:
                        cp = getattr(phase, "current_phase", None)
                        phase = getattr(cp, "value", str(cp)) if cp else None
                    risk = getattr(c, "risk_assessment", None)
                    risk_status = (
                        getattr(risk, "risk_level_name", None)
                        if risk is not None
                        else getattr(c, "risk_status", None)
                    )
                    action = getattr(getattr(c, "trade_setup", None), "action", None)
                    if action is not None and not isinstance(action, str):
                        action = getattr(action, "value", str(action))
                    elif action is None:
                        action = getattr(c, "action", None) or getattr(
                            multi_row, "next_action", None
                        )
                    rows.append(
                        ScreenCandidateRowView(
                            canonical_rank=rank,
                            ticker=str(getattr(c, "ticker", multi_row.ticker)),
                            accum_score=float(getattr(c, "accum_score", 0.0) or 0.0),
                            consecutive_streak=int(
                                getattr(c, "consecutive_streak", 0) or 0
                            ),
                            net_buy_ratio=float(getattr(c, "net_buy_ratio", 0.0) or 0.0),
                            bci_label=getattr(c, "bci_label", None),
                            setup_phase=str(phase) if phase else getattr(
                                multi_row, "setup_phase", None
                            ),
                            risk_status=str(
                                risk_status
                                or getattr(multi_row, "risk_status", None)
                                or "OPEN"
                            ),
                            action=str(action) if action else None,
                            signal_score=sig_score,
                            signal_authority_coverage=sig_cov,
                            window_shape_label=shape,
                            vwap_discount_pct=disc,
                            vwap_depth_label=depth,
                            window_accum=window_accum,
                            pattern=str(pattern) if pattern else None,
                        )
                    )
                else:
                    # Row present only on non-canonical windows: still list ticker.
                    sig_score, sig_cov = self._signal_fields(None, row=multi_row)
                    scores = [s for _, s in window_accum if s is not None]
                    # Prefer Disc% from any available window candidate.
                    disc, depth = None, None
                    for days, _ in window_accum:
                        cand = by_window.get(days)
                        if cand is not None:
                            disc, depth = self._vwap_fields(cand)
                            if disc is not None:
                                break
                    rows.append(
                        ScreenCandidateRowView(
                            canonical_rank=rank,
                            ticker=str(multi_row.ticker),
                            accum_score=max(scores) if scores else 0.0,
                            consecutive_streak=0,
                            net_buy_ratio=0.0,
                            bci_label=None,
                            setup_phase=getattr(multi_row, "setup_phase", None),
                            risk_status=str(
                                getattr(multi_row, "risk_status", None) or "OPEN"
                            ),
                            action=getattr(multi_row, "next_action", None),
                            signal_score=sig_score,
                            signal_authority_coverage=sig_cov,
                            window_shape_label=shape,
                            vwap_discount_pct=disc,
                            vwap_depth_label=depth,
                            window_accum=window_accum,
                            pattern=str(pattern) if pattern else None,
                        )
                    )
        else:
            candidates = getattr(projection, "candidates", [])
            for rank, c in enumerate(candidates, 1):
                raw_action = getattr(c, "action", None)
                if not isinstance(raw_action, str):
                    ts = getattr(c, "trade_setup", None)
                    act = getattr(ts, "action", None)
                    raw_action = getattr(act, "value", str(act)) if act else None

                raw_risk = getattr(c, "risk_status", None)
                if not isinstance(raw_risk, str):
                    ra = getattr(c, "risk_assessment", None)
                    raw_risk = getattr(ra, "risk_level_name", str(ra)) if ra else "OPEN"

                raw_phase = getattr(c, "setup_phase", None)
                if not isinstance(raw_phase, str) and raw_phase is not None:
                    cp = getattr(raw_phase, "current_phase", None)
                    raw_phase = getattr(cp, "value", str(cp)) if cp else None

                disc, depth = self._vwap_fields(c)
                sig_score, sig_cov = self._signal_fields(c)
                rows.append(
                    ScreenCandidateRowView(
                        canonical_rank=rank,
                        ticker=c.ticker,
                        accum_score=float(getattr(c, "accum_score", 0.0)),
                        consecutive_streak=int(getattr(c, "consecutive_streak", 0)),
                        net_buy_ratio=float(getattr(c, "net_buy_ratio", 0.0)),
                        bci_label=getattr(c, "bci_label", None),
                        setup_phase=str(raw_phase) if raw_phase else None,
                        risk_status=str(raw_risk) if raw_risk else "OPEN",
                        action=str(raw_action) if raw_action else None,
                        signal_score=sig_score,
                        signal_authority_coverage=sig_cov,
                        vwap_discount_pct=disc,
                        vwap_depth_label=depth,
                    )
                )

        result_status = resolve_accum_result_status(result_count=len(rows)).value
        related = tuple(
            ScreenRelatedActionView(
                verb=item["verb"],
                label=item["label"],
                command=item["command"],
            )
            for item in related_actions_for_accum(
                tickers=[row.ticker for row in rows],
                saved_watchlist_name=saved_name,
            )
        )
        return ScreenViewModel(
            active_tab=active_tab,
            universe_label=universe_label,
            candidate_rows=tuple(rows),
            watchlist_summaries=(),
            selected_snapshot_entries=(),
            comparison_result=None,
            warnings=warnings,
            result_status=result_status,
            related_actions=related,
            is_multi=is_multi,
            resolved_windows=resolved_windows,
        )

    def present_watchlists(
        self,
        list_result: ListScreenWatchlistsResult,
        *,
        active_tab: str = "SAVED_COMPARE",
    ) -> ScreenViewModel:
        return ScreenViewModel(
            active_tab=active_tab,
            universe_label="",
            candidate_rows=(),
            watchlist_summaries=list_result.summaries,
            selected_snapshot_entries=list_result.selected_entries,
            comparison_result=None,
            warnings=(),
        )

    def present_comparison(
        self,
        compare_result: CompareScreenWatchlistResult,
        *,
        active_tab: str = "SAVED_COMPARE",
    ) -> ScreenViewModel:
        comp = compare_result.comparison
        warnings = tuple(comp.warnings)
        return ScreenViewModel(
            active_tab=active_tab,
            universe_label=compare_result.saved_summary.universe,
            candidate_rows=(),
            watchlist_summaries=(compare_result.saved_summary,),
            selected_snapshot_entries=(),
            comparison_result=compare_result,
            warnings=warnings,
        )
