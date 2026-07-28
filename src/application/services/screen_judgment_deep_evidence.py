"""Optional analysis evidence for single-ticker screen judgment (ADR-054 S1).

Merges plan-era *analysis* evidence onto the screen desk without mutating
TradeSetup.action and without structure/sizing.

Layer: Application
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class ScreenJudgmentDeepEvidence:
    """Side-bag of optional judgment evidence for one ticker (not Action)."""

    ticker: str
    setup_name: str | None = None
    setup_eval: Any | None = None
    flow_detail: Any | None = None
    sentiment_response: Any | None = None
    sentiment_warning: str | None = None
    backtest_result: Any | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        setup_payload = None
        if self.setup_eval is not None and hasattr(self.setup_eval, "to_dict"):
            setup_payload = self.setup_eval.to_dict()
        flow_payload = None
        if self.flow_detail is not None and hasattr(self.flow_detail, "to_dict"):
            flow_payload = self.flow_detail.to_dict()
        elif self.flow_detail is not None:
            flow_payload = str(self.flow_detail)
        sentiment_payload = None
        if self.sentiment_response is not None and hasattr(self.sentiment_response, "to_dict"):
            sentiment_payload = self.sentiment_response.to_dict()
        backtest_payload = None
        if self.backtest_result is not None and hasattr(self.backtest_result, "to_dict"):
            backtest_payload = self.backtest_result.to_dict()
        return {
            "ticker": self.ticker,
            "setup_name": self.setup_name,
            "setup_eval": setup_payload,
            "flow_detail": flow_payload,
            "sentiment": sentiment_payload,
            "sentiment_warning": self.sentiment_warning,
            "strategy_backtest": backtest_payload,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ScreenJudgmentDeepEvidenceRequest:
    """Flags for optional analysis evidence (defaults all off)."""

    setup_name: str | None = None
    include_flow_detail: bool = False
    flow_window: int = 30
    include_sentiment: bool = False
    sentiment_verbose: bool = False
    include_strategy_evidence: bool = False
    strategy_name: str | None = None
    include_full: bool = False

    @property
    def any_enabled(self) -> bool:
        return bool(
            self.setup_name
            or self.include_flow_detail
            or self.include_sentiment
            or self.include_strategy_evidence
            or self.include_full
        )

    @property
    def wants_flow(self) -> bool:
        return self.include_full or self.include_flow_detail

    @property
    def wants_sentiment(self) -> bool:
        return self.include_full or self.include_sentiment

    @property
    def wants_strategy(self) -> bool:
        return bool(self.strategy_name) and (self.include_full or self.include_strategy_evidence)


def collect_screen_judgment_deep_evidence(
    *,
    ticker: str,
    as_of_date: date,
    candidate: Any | None,
    flags: ScreenJudgmentDeepEvidenceRequest,
    build_flow_detail: Callable[..., Any | None] | None = None,
    evaluate_setup: Callable[..., Any | None] | None = None,
    fetch_sentiment: Callable[..., tuple[Any | None, str | None]] | None = None,
    run_strategy_backtest: Callable[..., Any | None] | None = None,
) -> ScreenJudgmentDeepEvidence:
    """Collect optional evidence. Never mutates candidate.trade_setup / Action."""
    warnings: list[str] = []
    setup_eval = None
    flow_detail = None
    sentiment_response = None
    sentiment_warning = None
    backtest_result = None

    if flags.setup_name and evaluate_setup is not None:
        try:
            setup_eval = evaluate_setup(flags.setup_name, candidate)
        except Exception as exc:
            warnings.append(f"Setup lens unavailable: {exc}")

    if flags.wants_flow and build_flow_detail is not None:
        try:
            flow_detail = build_flow_detail(
                ticker=ticker,
                window_sessions=flags.flow_window,
                as_of_date=as_of_date,
            )
        except Exception as exc:
            warnings.append(f"Flow detail unavailable: {exc}")

    if flags.wants_sentiment and fetch_sentiment is not None:
        try:
            sentiment_response, sentiment_warning = fetch_sentiment(
                ticker=ticker,
                sentiment_verbose=flags.sentiment_verbose,
            )
        except Exception as exc:
            sentiment_warning = f"Sentiment fetch failed: {exc}"
            warnings.append(sentiment_warning)

    if flags.wants_strategy and run_strategy_backtest is not None and flags.strategy_name:
        try:
            backtest_result = run_strategy_backtest(
                ticker=ticker,
                strategy_name=flags.strategy_name,
            )
        except Exception as exc:
            warnings.append(f"Strategy evidence unavailable: {exc}")

    return ScreenJudgmentDeepEvidence(
        ticker=ticker.upper(),
        setup_name=flags.setup_name,
        setup_eval=setup_eval,
        flow_detail=flow_detail,
        sentiment_response=sentiment_response,
        sentiment_warning=sentiment_warning,
        backtest_result=backtest_result,
        warnings=tuple(warnings),
    )


def deep_evidence_action_fingerprint(candidate: Any | None) -> str | None:
    """Stable Action fingerprint for regression tests (no Action mutation)."""
    if candidate is None:
        return None
    setup = getattr(candidate, "trade_setup", None)
    if setup is None:
        return None
    action = getattr(setup, "action", None)
    if action is None:
        return None
    return getattr(action, "value", str(action))
