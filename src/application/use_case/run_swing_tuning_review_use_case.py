"""
RunSwingTuningReview use case - orchestrates the `saham trade tune-swing` command.

Owns --is-ratio validation, walk-forward IS/OOS split calculation, CLI
override/default normalization, backtest orchestration, review/patch payload
construction, and optional journal persistence. This is the workflow policy
previously embedded in the `tune-swing` CLI command.

Layer: Application
Depends on: SwingBacktestResponse, SwingTuningReviewJournal, and injected
backtest runner / document loader callables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from src.application.services.swing_tuning_contracts import (
    build_tuning_config_diff_draft,
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
)
from src.application.services.swing_tuning_review_journal import (
    SwingTuningReviewJournal,
)
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse

__all__ = [
    "RunSwingTuningReviewRequest",
    "RunSwingTuningReviewResult",
    "RunSwingTuningReviewUseCase",
    "SwingTuningRunnerDefaults",
]


@dataclass(frozen=True)
class SwingTuningRunnerDefaults:
    capital: int
    risk_pct: float
    max_positions: int
    take_profit_pct: float
    stop_loss_pct: float
    max_hold_days: int
    cost_bps: float


@dataclass(frozen=True)
class RunSwingTuningReviewRequest:
    tickers: list[str] | None
    universe: str | None
    setup: str
    start: str
    end: str | None
    capital: int | None
    risk_pct: float | None
    max_positions: int | None
    take_profit: float | None
    stop_loss: float | None
    max_hold: int | None
    cost_bps: float | None
    with_regime: bool
    allow_regimes: str | None
    benchmark: str
    db_path: Path | None
    output_format: str
    save: bool
    export_patch: bool
    is_ratio: float | None


@dataclass(frozen=True)
class RunSwingTuningReviewResult:
    response: SwingBacktestResponse
    payload: dict[str, Any]
    patch_payload: dict[str, Any] | None
    persistence: dict[str, Any] | None
    patch_export: dict[str, Any] | None
    is_split_message: str | None


BacktestRunner = Callable[..., SwingBacktestResponse]
DocumentLoader = Callable[[str], dict | None]


class RunSwingTuningReviewUseCase:
    def __init__(
        self,
        *,
        backtest_runner: BacktestRunner,
        runner_defaults: SwingTuningRunnerDefaults,
        document_loader: DocumentLoader,
        review_journal: SwingTuningReviewJournal | None = None,
    ) -> None:
        self._backtest_runner = backtest_runner
        self._runner_defaults = runner_defaults
        self._document_loader = document_loader
        self._review_journal = review_journal

    def execute(self, request: RunSwingTuningReviewRequest) -> RunSwingTuningReviewResult:
        is_ratio = request.is_ratio
        if is_ratio is not None:
            if request.end is None:
                raise ValueError(
                    "--is-ratio requires --end to define the full date range."
                )
            if not (0.0 < is_ratio < 1.0):
                raise ValueError(
                    f"--is-ratio must be in range (0.0, 1.0) exclusive, got {is_ratio}"
                )

        effective_end = request.end
        is_end_date: str | None = None
        oos_start_date: str | None = None
        is_split_message: str | None = None
        if is_ratio is not None and request.start and request.end:
            start_dt = date.fromisoformat(request.start)
            end_dt = date.fromisoformat(request.end)
            if start_dt >= end_dt:
                raise ValueError("--start must be before --end.")
            total_days = (end_dt - start_dt).days
            is_end_dt = start_dt + timedelta(days=int(total_days * is_ratio))
            oos_start_dt = is_end_dt + timedelta(days=1)
            if is_end_dt <= start_dt or oos_start_dt > end_dt:
                raise ValueError(
                    "--is-ratio requires a date range large enough to produce "
                    "non-empty IS and OOS windows."
                )
            effective_end = is_end_dt.isoformat()
            is_end_date = effective_end
            oos_start_date = oos_start_dt.isoformat()
            if request.output_format != "json":
                is_split_message = (
                    f"Walk-forward split: IS {request.start} -> {is_end_dt.isoformat()}  "
                    f"OOS {oos_start_dt.isoformat()} -> {request.end}"
                )

        defaults = self._runner_defaults
        resolved_capital = (
            request.capital if request.capital is not None else defaults.capital
        )
        resolved_risk_pct = (
            request.risk_pct if request.risk_pct is not None else defaults.risk_pct
        )
        resolved_max_positions = (
            request.max_positions
            if request.max_positions is not None
            else defaults.max_positions
        )
        resolved_take_profit = (
            request.take_profit
            if request.take_profit is not None
            else defaults.take_profit_pct
        )
        resolved_stop_loss = (
            request.stop_loss if request.stop_loss is not None else defaults.stop_loss_pct
        )
        resolved_max_hold = (
            request.max_hold if request.max_hold is not None else defaults.max_hold_days
        )
        resolved_cost_bps = (
            request.cost_bps if request.cost_bps is not None else defaults.cost_bps
        )

        response = self._backtest_runner(
            tickers=request.tickers,
            universe=request.universe,
            setup=request.setup,
            start=request.start,
            end=effective_end,
            capital=resolved_capital,
            risk_pct=resolved_risk_pct,
            max_positions=resolved_max_positions,
            take_profit=resolved_take_profit,
            stop_loss=resolved_stop_loss,
            max_hold=resolved_max_hold,
            cost_bps=resolved_cost_bps,
            with_regime=request.with_regime,
            allow_regimes=request.allow_regimes,
            benchmark=request.benchmark,
            db_path=request.db_path,
            announce=request.output_format != "json",
        )

        payload = self._build_review_payload(response)
        if is_ratio is not None:
            payload["is_ratio"] = round(is_ratio, 4)
            if is_end_date and oos_start_date and request.end:
                payload["is_end_date"] = is_end_date
                payload["oos_start_date"] = oos_start_date
                payload["full_end_date"] = request.end
                oos_response = self._backtest_runner(
                    tickers=request.tickers,
                    universe=request.universe,
                    setup=request.setup,
                    start=oos_start_date,
                    end=request.end,
                    capital=resolved_capital,
                    risk_pct=resolved_risk_pct,
                    max_positions=resolved_max_positions,
                    take_profit=resolved_take_profit,
                    stop_loss=resolved_stop_loss,
                    max_hold=resolved_max_hold,
                    cost_bps=resolved_cost_bps,
                    with_regime=request.with_regime,
                    allow_regimes=request.allow_regimes,
                    benchmark=request.benchmark,
                    db_path=request.db_path,
                    announce=False,
                )
                payload["oos_backtest_summary"] = {
                    "trade_count": oos_response.trade_count,
                    "total_return_pct": oos_response.total_return_pct,
                    "win_rate_pct": oos_response.win_rate_pct,
                    "max_drawdown_pct": oos_response.max_drawdown_pct,
                    "avg_trade_return_pct": oos_response.avg_trade_return_pct,
                    "profit_factor": oos_response.profit_factor,
                }

        persistence: dict[str, Any] | None = None
        if request.save:
            if self._review_journal is None:
                raise ValueError("--save requires a configured review journal.")
            save_result = self._review_journal.append_review(payload)
            persistence = {**save_result.to_dict()}
            payload["persistence"] = persistence

        patch_payload: dict[str, Any] | None = None
        if request.export_patch:
            patch_payload = self._build_patch_payload(payload)

        return RunSwingTuningReviewResult(
            response=response,
            payload=payload,
            patch_payload=patch_payload,
            persistence=persistence,
            patch_export=None,
            is_split_message=is_split_message,
        )

    def _build_review_payload(self, response: SwingBacktestResponse) -> dict[str, Any]:
        plan = build_tuning_readiness_plan(response.attribution_summary)
        proposal = build_tuning_proposal_draft(response.attribution_summary)
        active_setups = frozenset({response.setup}) if response.setup else None
        config_diff = build_tuning_config_diff_draft(
            response.attribution_summary,
            document_loader=self._document_loader,
            active_setups=active_setups,
        )
        return {
            "schema_version": 1,
            "artifact_type": "swing_tuning_review",
            "intent": "deterministic_backtest_attribution_to_config_review_no_apply",
            "setup": response.setup,
            "start_date": response.start_date.isoformat(),
            "end_date": response.end_date.isoformat(),
            "sample": response.attribution_summary.sample_quality.to_dict(),
            "backtest_summary": {
                "initial_capital": str(response.initial_capital),
                "final_equity": str(response.final_equity),
                "total_return_pct": response.total_return_pct,
                "max_drawdown_pct": response.max_drawdown_pct,
                "trade_count": response.trade_count,
                "win_rate_pct": response.win_rate_pct,
                "avg_trade_return_pct": response.avg_trade_return_pct,
                "profit_factor": response.profit_factor,
                "candidate_observation_count": len(response.candidate_observations),
            },
            "attribution_summary": response.attribution_summary.to_dict(),
            "tuning_plan": plan.to_dict(),
            "tuning_proposal": proposal.to_dict(),
            "tuning_config_diff": config_diff.to_dict(),
            "apply": {
                "supported": False,
                "reason": "This command is review-only. Edit YAML manually after human review.",
            },
        }

    def _build_patch_payload(self, review_payload: dict[str, Any]) -> dict[str, Any]:
        tuning_config_diff = review_payload.get("tuning_config_diff") or {}
        diff_items = tuning_config_diff.get("diff_items") or []
        patch_items = [
            {
                "target_path": item.get("target_path"),
                "parsed_target_path": item.get("parsed_target_path"),
                "current_value": item.get("current_value"),
                "proposed_value": item.get("proposed_value"),
                "rationale": item.get("rationale"),
                "confidence": item.get("confidence"),
                "status": item.get("status"),
                "value_selection_policy": item.get("value_selection_policy"),
                "target_classification": item.get("target_classification"),
                "evidence_snapshot": item.get("evidence_snapshot"),
                "evidence_dimensions": item.get("evidence_dimensions"),
            }
            for item in diff_items
            if item.get("proposed_value") is not None
        ]
        return {
            "schema_version": 1,
            "artifact_type": "swing_tuning_patch_review",
            "intent": "review_only_candidate_config_patch_no_apply",
            "source_review": {
                "setup": review_payload.get("setup"),
                "start_date": review_payload.get("start_date"),
                "end_date": review_payload.get("end_date"),
                "sample": review_payload.get("sample"),
                "backtest_summary": review_payload.get("backtest_summary"),
                "tuning_config_diff_status": tuning_config_diff.get("status"),
                "tuning_config_diff_summary": tuning_config_diff.get("summary"),
                "is_ratio": review_payload.get("is_ratio"),
                "is_end_date": review_payload.get("is_end_date"),
                "oos_start_date": review_payload.get("oos_start_date"),
                "full_end_date": review_payload.get("full_end_date"),
                "oos_backtest_summary": review_payload.get("oos_backtest_summary"),
                "walk_forward_enforced": review_payload.get("is_end_date") is not None,
            },
            "patch_items": patch_items,
            "item_count": len(patch_items),
            "apply": {
                "supported": False,
                "reason": "Patch export is review-only and must not mutate YAML.",
            },
        }
