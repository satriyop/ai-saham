"""Single request builder for `screen accum` (CLI defaults + TUI cockpit).

Both adapters must build ``RunAccumulationScreenWorkflowRequest`` through this
module so window/sort/top/filter defaults cannot drift independently.

Layer: Adapter composition (no IO)
"""

from __future__ import annotations

from datetime import date

from src.application.services.screen_judgment_diagnostic_evidence import (
    ScreenJudgmentDiagnosticEvidenceRequest,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
)

# Canonical CLI / cockpit defaults (must stay aligned with Typer defaults).
DEFAULT_WINDOW = 7
DEFAULT_TOP = 20
DEFAULT_SORT_BY = "signal"
DEFAULT_MIN_STREAK = 0
DEFAULT_MIN_PIOTROSKI = 0
DEFAULT_MULTI_WINDOWS: tuple[int, ...] = (7, 30, 90)


def build_screen_accum_request(
    *,
    tickers: list[str],
    universe_label: str,
    universe_name: str | None = None,
    window: int = DEFAULT_WINDOW,
    min_streak: int = DEFAULT_MIN_STREAK,
    min_accum_score: float | None = None,
    min_signal_score: float | None = None,
    min_piotroski: int = DEFAULT_MIN_PIOTROSKI,
    strategy_name: str | None = None,
    include_strategy_overlay: bool | None = None,
    multi: bool = False,
    windows: list[int] | None = None,
    top: int = DEFAULT_TOP,
    save_name: str | None = None,
    save_enabled: bool | None = None,
    vwap_only: bool = False,
    squeeze_only: bool = False,
    sort_by: str = DEFAULT_SORT_BY,
    as_of_date: date | None = None,
    diagnostic_evidence: ScreenJudgmentDiagnosticEvidenceRequest | None = None,
) -> RunAccumulationScreenWorkflowRequest:
    """Build the workflow request for one screen-accum run.

    CLI passes flag values; TUI passes defaults (or explicit overrides).
    ``include_strategy_overlay`` defaults to True when ``strategy_name`` is set.
    ``save_enabled`` defaults to True when ``save_name`` is set.
    ``diagnostic_evidence`` defaults to all-off (universe-safe).
    """
    if include_strategy_overlay is None:
        include_strategy_overlay = bool(strategy_name)
    if save_enabled is None:
        save_enabled = bool(save_name)

    if multi:
        window_list = list(windows) if windows is not None else list(DEFAULT_MULTI_WINDOWS)
    else:
        window_list = list(windows) if windows is not None else []

    return RunAccumulationScreenWorkflowRequest(
        tickers=list(tickers),
        universe_label=universe_label,
        universe_name=universe_name,
        window=window,
        min_streak=min_streak,
        min_accum_score=min_accum_score,
        min_signal_score=min_signal_score,
        min_piotroski=min_piotroski,
        strategy_name=strategy_name,
        include_strategy_overlay=include_strategy_overlay,
        multi=multi,
        windows=window_list,
        top=top,
        save_name=save_name,
        save_enabled=save_enabled,
        vwap_only=vwap_only,
        squeeze_only=squeeze_only,
        sort_by=sort_by,
        as_of_date=as_of_date,
        diagnostic_evidence=diagnostic_evidence or ScreenJudgmentDiagnosticEvidenceRequest(),
    )


def build_default_screen_accum_request(
    *,
    tickers: list[str],
    universe: str,
) -> RunAccumulationScreenWorkflowRequest:
    """Cockpit / default CLI-equivalent single-window screen (no multi, no save)."""
    label = universe or f"{len(tickers)} tickers"
    return build_screen_accum_request(
        tickers=tickers,
        universe_label=label,
        universe_name=universe or None,
    )
