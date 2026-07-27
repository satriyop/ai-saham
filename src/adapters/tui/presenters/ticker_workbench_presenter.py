"""Per-tab view model for the Ticker Decision Workbench.

Splits one typed ``SwingAnalysisWorkflowResponse`` into a persistent decision
strip plus Overview / Setup / Signal & Risk tab sections. The presenter performs
no financial math and never lets setup fit or the optional preview stand in for
the canonical ``TradeSetup.action``.

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.swing_analysis import (
    SignalAssessmentStatus,
    SwingAnalysisWorkflowResponse,
)
from src.domain.value_objects.trade_setup import SetupAction

from .ticker_research_presenter import _enum_value, _flatten, _risk_name

# Evidence keys grouped per tab. Any evidence key not named here falls through to
# the Signal & Risk tab so no section is silently dropped.
_SETUP_KEYS = frozenset(
    {"setup", "setup_evidence", "setup_phase", "strategy", "strategy_rule_evidence"}
)
_OVERVIEW_KEYS = frozenset({"accumulation", "foreign_flow_evidence", "flow", "regime", "sentiment"})

# Canonical action -> (symbol, semantic severity stem). Keyed on the domain
# SetupAction enum (never string literals) so the TUI displays the canonical
# vocabulary without ever redefining it; blocked actions share bearish severity
# but keep their explicit BLOCKED text. Looked up by ``.value`` at runtime.
_ACTION_STYLE: dict[SetupAction, tuple[str, str]] = {
    SetupAction.ENTER: ("▲", "bullish"),
    SetupAction.WATCH: ("◆", "caution"),
    SetupAction.AVOID: ("▼", "bearish"),
    SetupAction.BLOCKED_EXECUTION: ("■", "bearish"),
    SetupAction.BLOCKED_STRUCTURAL: ("■", "bearish"),
}
_ACTION_STYLE_BY_VALUE: dict[str, tuple[str, str]] = {
    action.value: style for action, style in _ACTION_STYLE.items()
}


@dataclass(frozen=True)
class VerdictBadge:
    """Explicit symbol + text + severity so status never relies on color alone."""

    symbol: str
    text: str
    severity: str  # bullish | caution | bearish | unavailable | info


@dataclass(frozen=True)
class DecisionStripView:
    ticker: str
    badge: VerdictBadge
    signal_status: str
    signal_score: int | None
    signal_coverage: float | None
    risk: str | None
    regime: str | None
    setup_name: str | None
    setup_match: str | None
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class TickerWorkbenchViewModel:
    source: SwingAnalysisWorkflowResponse
    ticker: str
    decision: DecisionStripView
    overview: tuple[tuple[str, str], ...]
    setup: tuple[tuple[str, str], ...]
    signal_risk: tuple[tuple[str, str], ...]
    preview: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]


def _badge(availability, trade_setup) -> VerdictBadge:
    available = availability.status is SignalAssessmentStatus.AVAILABLE
    if not available or trade_setup is None:
        return VerdictBadge("—", "UNAVAILABLE", "unavailable")
    action = _enum_value(trade_setup.action)
    symbol, severity = _ACTION_STYLE_BY_VALUE.get(str(action), ("•", "info"))
    return VerdictBadge(symbol, str(action), severity)


def _setup_fields(evidence_dict: dict) -> tuple[str | None, str | None]:
    setup = evidence_dict.get("setup")
    if not isinstance(setup, dict):
        return None, None
    return setup.get("name"), setup.get("match")


class TickerWorkbenchPresenter:
    def present(self, response: SwingAnalysisWorkflowResponse) -> TickerWorkbenchViewModel:
        verdict = response.verdict
        evidence = response.evidence
        diagnostics = response.diagnostics
        if verdict is None or evidence is None or diagnostics is None:
            raise ValueError("swing response omitted typed verdict/evidence/diagnostics")

        availability = verdict.signal_assessment_availability
        available = availability.status is SignalAssessmentStatus.AVAILABLE
        signal = verdict.signal_assessment if available else None
        trade_setup = verdict.trade_setup if available else None

        evidence_dict = evidence.to_dict()
        setup_name, setup_match = _setup_fields(evidence_dict)

        decision = DecisionStripView(
            ticker=response.ticker,
            badge=_badge(availability, trade_setup),
            signal_status=availability.status.value,
            signal_score=signal.assessment.score if signal else None,
            signal_coverage=(signal.assessment.signal_authority_coverage if signal else None),
            risk=_risk_name(verdict.risk_response),
            regime=_enum_value(verdict.market_regime.regime) if verdict.market_regime else None,
            setup_name=setup_name,
            setup_match=setup_match,
            # Canonical blockers only; never fabricated when the field is absent.
            blockers=(
                tuple(getattr(trade_setup, "blocking_gates", ()) or ())
                if trade_setup is not None
                else ()
            ),
        )

        overview: dict = {}
        setup: dict = {}
        signal_risk: dict = {}
        for key, value in evidence_dict.items():
            if key in _SETUP_KEYS:
                setup[key] = value
            elif key in _OVERVIEW_KEYS:
                overview[key] = value
            else:
                signal_risk[key] = value

        signal_risk_rows = _flatten(signal_risk) + _flatten(diagnostics.to_dict())

        preview = _flatten(
            {
                "signal": (
                    verdict.market_context_signal_preview.assessment.score
                    if verdict.market_context_signal_preview
                    else None
                ),
                "risk": _risk_name(verdict.market_context_risk_preview),
                "action": (
                    _enum_value(verdict.market_context_trade_setup_preview.action)
                    if verdict.market_context_trade_setup_preview
                    else None
                ),
            }
        )

        return TickerWorkbenchViewModel(
            source=response,
            ticker=response.ticker,
            decision=decision,
            overview=_flatten(overview) if overview else (("overview", "— UNAVAILABLE"),),
            setup=_flatten(setup) if setup else (("setup", "— UNAVAILABLE"),),
            signal_risk=signal_risk_rows or (("signal_risk", "— UNAVAILABLE"),),
            preview=preview,
            warnings=tuple(response.warnings),
        )
