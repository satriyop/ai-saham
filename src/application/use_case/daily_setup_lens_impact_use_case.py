"""
Bounded, read-only setup-lens impact use case for the CLI `today` command.

For each accumulation candidate already selected by the daily briefing, evaluate
every canonical swing setup lens in ``AVAILABLE_SWING_SETUPS`` using the SAME
canonical ``SwingAnalysisWorkflowUseCase`` that ``saham analyze swing
TICKER --setup SETUP`` uses. The workflow is invoked in a bounded read-only mode
(no auto/force refresh, no strategy backtest, no sentiment) so no fetch, write,
journal, or AI side effects occur.

This use case does NOT construct infrastructure. The four setup-bound workflow
instances are injected by the adapter, keyed by setup name. It also does NOT
re-rank or re-cap candidates: it evaluates exactly what it is given, in order.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Mapping

from src.application.dto.swing_analysis import (
    SwingAnalysisWorkflowRequest,
    SwingAnalysisWorkflowResponse,
)
from src.application.use_case.evaluate_swing_setup_use_case import AVAILABLE_SWING_SETUPS
from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisDataUnavailable,
    SwingAnalysisWorkflowUseCase,
)

# Only setup entry-authority / phase-gate constraint reasons justify a
# ``(no-entry)`` cap label in the today setup-lens table. These are the reasons
# produced by the ``if entry_quality == EntryQuality.ENTER:`` block in
# ``DecisionPolicyService`` (see src/application/services/decision_policy.py).
# Generic score/coverage/conviction/regime/phase-quality reasons describe why a
# score was capped, not a setup-specific entry-authority restriction, so they are
# deliberately excluded here (T8 scope).
_ENTRY_AUTHORITY_REASON_MARKERS: tuple[str, ...] = (
    "has no standalone entry authority",
    "requires setup phase for ENTER",
    "requires phase",
)


def _entry_authority_constraint_reasons(reasons: tuple[str, ...]) -> list[str]:
    return [
        reason
        for reason in reasons
        if any(marker in reason for marker in _ENTRY_AUTHORITY_REASON_MARKERS)
    ]


@dataclass(frozen=True)
class SwingLensRequestDefaults:
    """Typed request-shaping config for building read-only swing requests.

    These are the deterministic knobs that ``saham analyze swing`` sources from
    app/analyze-swing config. They are injected once by the adapter so this use
    case never hardcodes numeric analysis parameters.
    """

    window: int
    flow_window: int
    risk_pct: float
    atr_mult: float
    rr: float
    regime_universe: str
    benchmark: str
    db_path: Path


@dataclass(frozen=True)
class DailySetupLensImpactCandidate:
    ticker: str
    base_action: str | None  # from DailyAccumulationCandidate.action, passed in by caller


@dataclass(frozen=True)
class DailySetupLensImpactRequest:
    candidates: tuple[DailySetupLensImpactCandidate, ...]
    as_of_date: date


@dataclass(frozen=True)
class DailySetupLensImpactCell:
    setup_name: str
    action: str | None
    signal_score: int | None
    setup_match: str
    entry_authority: bool | None
    capped_reason: str | None
    warning: str | None = None


@dataclass(frozen=True)
class DailySetupLensImpactRow:
    ticker: str
    base_action: str | None
    cells: tuple[DailySetupLensImpactCell, ...]


@dataclass(frozen=True)
class DailySetupLensImpactResult:
    rows: tuple[DailySetupLensImpactRow, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


class DailySetupLensImpactUseCase:
    """Evaluate canonical swing setup lenses for already-selected candidates.

    Read-only: builds each ``SwingAnalysisWorkflowRequest`` with
    ``auto_refresh=False``, ``force_refresh=False``, ``strategy_name=None`` and
    ``include_sentiment=False`` so the canonical workflow performs no fetch,
    write, journal, or AI work.
    """

    def __init__(
        self,
        setup_workflows: Mapping[str, SwingAnalysisWorkflowUseCase],
        request_defaults: SwingLensRequestDefaults,
    ) -> None:
        expected = set(AVAILABLE_SWING_SETUPS)
        provided = set(setup_workflows.keys())
        if provided != expected:
            raise ValueError(
                "setup_workflows keys must exactly match AVAILABLE_SWING_SETUPS; "
                f"expected {sorted(expected)}, got {sorted(provided)}"
            )
        self._setup_workflows = dict(setup_workflows)
        self._defaults = request_defaults

    def execute(self, request: DailySetupLensImpactRequest) -> DailySetupLensImpactResult:
        if not request.candidates:
            return DailySetupLensImpactResult(rows=())

        rows: list[DailySetupLensImpactRow] = []
        for candidate in request.candidates:
            cells: list[DailySetupLensImpactCell] = []
            for setup_name in AVAILABLE_SWING_SETUPS:
                cells.append(
                    self._evaluate_cell(
                        ticker=candidate.ticker,
                        setup_name=setup_name,
                        as_of_date=request.as_of_date,
                    )
                )
            rows.append(
                DailySetupLensImpactRow(
                    ticker=candidate.ticker,
                    base_action=candidate.base_action,
                    cells=tuple(cells),
                )
            )
        return DailySetupLensImpactResult(rows=tuple(rows))

    def _evaluate_cell(
        self,
        *,
        ticker: str,
        setup_name: str,
        as_of_date: date,
    ) -> DailySetupLensImpactCell:
        workflow = self._setup_workflows[setup_name]
        req = self._build_request(ticker=ticker, setup_name=setup_name, as_of_date=as_of_date)
        try:
            response = workflow.execute(req)
        except SwingAnalysisDataUnavailable as exc:
            return DailySetupLensImpactCell(
                setup_name=setup_name,
                action=None,
                signal_score=None,
                setup_match="NO_MATCH",
                entry_authority=None,
                capped_reason=None,
                warning=f"No local candle data for {exc.ticker}",
            )
        return self._map_response(setup_name=setup_name, response=response)

    def _build_request(
        self,
        *,
        ticker: str,
        setup_name: str,
        as_of_date: date,
    ) -> SwingAnalysisWorkflowRequest:
        d = self._defaults
        return SwingAnalysisWorkflowRequest(
            ticker=ticker,
            today=as_of_date,
            strategy_name=None,
            setup_name=setup_name,
            window=d.window,
            flow_window=d.flow_window,
            capital=None,
            risk_pct=d.risk_pct,
            entry_price=None,
            atr_mult=d.atr_mult,
            rr=d.rr,
            include_sentiment=False,
            include_flow_detail=False,
            include_signal_detail=False,
            include_risk_detail=False,
            include_market_detail=False,
            sentiment_verbose=False,
            auto_refresh=False,
            force_refresh=False,
            with_market_context=False,
            regime_universe=d.regime_universe,
            benchmark=d.benchmark,
            db_path=d.db_path,
            with_technical_gate=False,
        )

    def _map_response(
        self,
        *,
        setup_name: str,
        response: SwingAnalysisWorkflowResponse,
    ) -> DailySetupLensImpactCell:
        trade_setup = response.trade_setup
        signal_assessment = response.signal_assessment
        setup_eval = response.setup_eval

        action = trade_setup.action.value if trade_setup is not None else None

        if trade_setup is not None:
            signal_score: int | None = trade_setup.signal_score
        elif signal_assessment is not None:
            signal_score = signal_assessment.assessment.score
        else:
            signal_score = None

        setup_match = setup_eval.match.value if setup_eval is not None else "NO_MATCH"
        entry_authority = setup_eval.entry_authority if setup_eval is not None else None

        capped_reason: str | None = None
        if signal_assessment is not None:
            constraints = signal_assessment.assessment.decision_constraints
            if constraints is not None and constraints.constraint_reasons:
                matching = _entry_authority_constraint_reasons(
                    tuple(constraints.constraint_reasons)
                )
                capped_reason = "; ".join(matching) if matching else None

        return DailySetupLensImpactCell(
            setup_name=setup_name,
            action=action,
            signal_score=signal_score,
            setup_match=setup_match,
            entry_authority=entry_authority,
            capped_reason=capped_reason,
            warning=None,
        )
