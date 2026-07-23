"""
RunAccumulationAuditWorkflow use case - orchestrates accumulation evaluate.

Owns setup-preset resolution, CLI option/default normalization, date/trend/grid
parsing, and ticker resolution before delegating to AccumulationAuditUseCase.
This is the workflow policy previously embedded in the accumulation CLI command.

Public CLI path: `saham research accumulation evaluate`.

Layer: Application
Depends on: AccumulationAuditUseCase, AccumulationAuditPolicy, and an injected
ticker-resolver callable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Protocol

from src.application.dto.accumulation_audit import (
    AccumulationAuditPolicy,
    AccumulationAuditRequest,
    AccumulationAuditResponse,
)

__all__ = [
    "NoTickersError",
    "RunAccumulationAuditWorkflowRequest",
    "RunAccumulationAuditWorkflowResult",
    "RunAccumulationAuditWorkflowUseCase",
]


class NoTickersError(ValueError):
    """Raised when ticker resolution yields an empty list.

    Kept distinct from ValueError so adapters can render the CLI's original
    unprefixed message instead of the generic "Error: <message>" wrapper.
    """

_DEFAULT_WINDOW = 7
_DEFAULT_MIN_FOREIGN_FLOW_SCORE = 40.0
_DEFAULT_MIN_NET_BUY_DAYS = 2
_DEFAULT_TAKE_PROFITS = "4,5,6"
_DEFAULT_STOP_LOSSES = "3,5,7"
_DEFAULT_MAX_HOLDS = "3,5,7,10"
_VALID_TRENDS = {"UP", "SIDE", "DOWN"}


class AuditRunner(Protocol):
    """Port-shaped dependency: anything that can execute an audit request."""

    def execute(self, request: AccumulationAuditRequest) -> AccumulationAuditResponse: ...


TickerResolver = Callable[..., list[str]]


@dataclass(frozen=True)
class RunAccumulationAuditWorkflowRequest:
    tickers: list[str]
    universe: str | None
    setup: str | None
    start: str
    end: str | None
    window: int | None
    min_accum_score: float | None
    min_net_buy_days: int | None
    min_vwap_disc: float | None
    trend: str | None
    min_flow_pct: float | None
    require_rsi: bool
    max_rsi: float | None
    min_rsi: float | None
    max_bb_width_pctile: float | None
    broker_quality: str | None
    simulate_exits: bool | None
    take_profits: str | None
    stop_losses: str | None
    max_holds: str | None
    horizon: int | None


@dataclass(frozen=True)
class RunAccumulationAuditWorkflowResult:
    response: AccumulationAuditResponse
    ticker_count: int
    start_date: date
    end_date: date
    window: int
    min_accum_score: float
    filter_label: str
    resolved_tickers: tuple[str, ...]

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize the accumulation_audit artifact (schema_version 2, DQ-008)."""
        response = self.response
        return {
            "schema_version": 2,
            "artifact_type": "accumulation_audit",
            "start_date": response.start_date.isoformat(),
            "end_date": response.end_date.isoformat(),
            "window_days": response.window_days,
            "total_replay_dates": response.total_replay_dates,
            "total_tickers": response.total_tickers,
            "total_records": response.total_records,
            "skipped_no_forward_data": response.skipped_no_forward_data,
            "skip_ledger": response.skip_ledger.to_dict(),
            "claim_stamp": response.claim_stamp.to_dict(),
            "warnings": response.warnings,
            "group_stats": [s.to_dict() for s in response.group_stats],
            "exit_simulations": [s.to_dict() for s in response.exit_simulations],
            "records_in_json": response.claim_stamp.records_in_json,
        }


def _parse_float_grid(value: str, option_name: str) -> tuple[float, ...]:
    try:
        parsed = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as e:
        raise ValueError(f"{option_name} must be comma-separated numbers") from e
    if not parsed or any(item <= 0 for item in parsed):
        raise ValueError(f"{option_name} must contain positive numbers")
    return parsed


def _parse_int_grid(value: str, option_name: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as e:
        raise ValueError(f"{option_name} must be comma-separated integers") from e
    if not parsed or any(item <= 0 for item in parsed):
        raise ValueError(f"{option_name} must contain positive integers")
    return parsed


class RunAccumulationAuditWorkflowUseCase:
    """Orchestrates setup resolution, parsing, ticker resolution, and the audit replay."""

    def __init__(
        self,
        *,
        audit_use_case: AuditRunner,
        audit_policy: AccumulationAuditPolicy,
        audit_setups: dict[str, dict[str, Any]],
        resolve_tickers: TickerResolver,
    ) -> None:
        self._audit_use_case = audit_use_case
        self._audit_policy = audit_policy
        self._audit_setups = audit_setups
        self._resolve_tickers = resolve_tickers

    def execute(
        self, request: RunAccumulationAuditWorkflowRequest
    ) -> RunAccumulationAuditWorkflowResult:
        setup_values = self._resolve_setup(request.setup)

        universe = request.universe or setup_values.get("universe")
        window = (
            request.window if request.window is not None
            else int(setup_values.get("window", _DEFAULT_WINDOW))
        )
        min_accum_score = (
            request.min_accum_score if request.min_accum_score is not None
            else float(setup_values.get("min_accum_score", _DEFAULT_MIN_FOREIGN_FLOW_SCORE))
        )
        min_net_buy_days = (
            request.min_net_buy_days if request.min_net_buy_days is not None
            else int(setup_values.get("min_net_buy_days", _DEFAULT_MIN_NET_BUY_DAYS))
        )
        min_vwap_disc = (
            request.min_vwap_disc if request.min_vwap_disc is not None
            else setup_values.get("min_vwap_disc")
        )
        trend = request.trend or setup_values.get("trend")
        min_flow_pct = (
            request.min_flow_pct if request.min_flow_pct is not None
            else setup_values.get("min_flow_pct")
        )
        require_rsi = request.require_rsi or bool(setup_values.get("require_rsi", False))
        max_rsi = (
            request.max_rsi if request.max_rsi is not None else setup_values.get("max_rsi")
        )
        min_rsi = (
            request.min_rsi if request.min_rsi is not None else setup_values.get("min_rsi")
        )
        max_bb_width_pctile = (
            request.max_bb_width_pctile if request.max_bb_width_pctile is not None
            else setup_values.get("max_bb_width_pctile")
        )
        broker_quality = request.broker_quality or setup_values.get("broker_quality")
        simulate_exits = (
            request.simulate_exits if request.simulate_exits is not None
            else bool(setup_values.get("simulate_exits", False))
        )
        take_profits = request.take_profits or str(
            setup_values.get("take_profits", _DEFAULT_TAKE_PROFITS)
        )
        stop_losses = request.stop_losses or str(
            setup_values.get("stop_losses", _DEFAULT_STOP_LOSSES)
        )
        max_holds = request.max_holds or str(setup_values.get("max_holds", _DEFAULT_MAX_HOLDS))
        resolved_horizon = (
            request.horizon if request.horizon is not None
            else max(self._audit_policy.forward_return_horizons)
        )

        try:
            start_date = date.fromisoformat(request.start)
            end_date = date.fromisoformat(request.end) if request.end else date.today()
        except ValueError as e:
            raise ValueError(f"invalid date format: {e}") from e

        ticker_list = self._resolve_tickers(
            universe=universe,
            explicit=request.tickers,
        )
        if not ticker_list:
            raise NoTickersError(
                "No tickers to audit. Specify --universe or provide ticker arguments."
            )

        trend_filter = trend.upper() if trend else None
        if trend_filter is not None and trend_filter not in _VALID_TRENDS:
            raise ValueError("--trend must be one of: UP, SIDE, DOWN")

        filter_label = self._build_filter_label(
            min_vwap_disc=min_vwap_disc,
            trend_filter=trend_filter,
            min_flow_pct=min_flow_pct,
            require_rsi=require_rsi,
            max_rsi=max_rsi,
            min_rsi=min_rsi,
            max_bb_width_pctile=max_bb_width_pctile,
            broker_quality=broker_quality,
            simulate_exits=simulate_exits,
        )

        take_profit_grid = _parse_float_grid(take_profits, "--take-profits")
        stop_loss_grid = _parse_float_grid(stop_losses, "--stop-losses")
        max_hold_grid = _parse_int_grid(max_holds, "--max-holds")

        response = self._audit_use_case.execute(
            AccumulationAuditRequest(
                tickers=ticker_list,
                start_date=start_date,
                end_date=end_date,
                window_days=window,
                min_net_buy_days=min_net_buy_days,
                min_accum_score=min_accum_score,
                horizon_days=resolved_horizon,
                min_vwap_disc_pct=min_vwap_disc,
                trend=trend_filter,
                min_flow_pct=min_flow_pct,
                require_rsi=require_rsi,
                min_rsi=min_rsi,
                max_rsi=max_rsi,
                max_bb_width_pctile=max_bb_width_pctile,
                broker_quality=broker_quality,
                simulate_exits=simulate_exits,
                take_profit_pcts=take_profit_grid,
                stop_loss_pcts=stop_loss_grid,
                max_hold_days=max_hold_grid,
                policy=self._audit_policy,
            )
        )

        return RunAccumulationAuditWorkflowResult(
            response=response,
            ticker_count=len(ticker_list),
            start_date=start_date,
            end_date=end_date,
            window=window,
            min_accum_score=min_accum_score,
            filter_label=filter_label,
            resolved_tickers=tuple(ticker_list),
        )

    def _resolve_setup(self, setup: str | None) -> dict[str, Any]:
        if setup is None:
            return {}
        setup_name = setup.lower()
        if setup_name not in self._audit_setups:
            available = ", ".join(self._audit_setups)
            raise ValueError(f"unknown setup '{setup}'. Available setups: {available}")
        return self._audit_setups[setup_name]

    @staticmethod
    def _build_filter_label(
        *,
        min_vwap_disc: float | None,
        trend_filter: str | None,
        min_flow_pct: float | None,
        require_rsi: bool,
        max_rsi: float | None,
        min_rsi: float | None,
        max_bb_width_pctile: float | None,
        broker_quality: str | None,
        simulate_exits: bool,
    ) -> str:
        filter_parts = []
        if min_vwap_disc is not None:
            filter_parts.append(f"VWAP>={min_vwap_disc:g}%")
        if trend_filter is not None:
            filter_parts.append(f"trend={trend_filter}")
        if min_flow_pct is not None:
            filter_parts.append(f"flow>={min_flow_pct:g}%")
        if require_rsi:
            filter_parts.append("RSI present")
        if max_rsi is not None:
            filter_parts.append(f"RSI<={max_rsi:g}")
        if min_rsi is not None:
            filter_parts.append(f"RSI>={min_rsi:g}")
        if max_bb_width_pctile is not None:
            filter_parts.append(f"BBpct<={max_bb_width_pctile:g}")
        if broker_quality is not None:
            filter_parts.append(f"broker={broker_quality}")
        if simulate_exits:
            filter_parts.append("exit simulation")
        return f" | filters: {', '.join(filter_parts)}" if filter_parts else ""
