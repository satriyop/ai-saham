"""
Application use case: log a swing trade candidate to the accumulation journal.

Orchestrates: single-ticker screen → multi-window pattern → entry price resolution
→ gate evaluation (optional) → regime computation (optional) → CSV write → JSONL
dual-write (optional).

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from src.application.use_case.accumulation_screen import (
    AccumulationScreenRequest,
    classify_multi_window_pattern,
    compute_percent_plan,
    evaluate_foreign_bounce_gates,
)

if TYPE_CHECKING:
    from src.application.services.accumulation_journal import AccumulationJournalService
    from src.application.use_case.accumulation_screen import (
        AccumulationCandidate,
        AccumulationScreenUseCase,
    )
    from src.application.use_case.market_regime import MarketRegimeUseCase
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.ports.trade_journal_store import TradeJournalStore


@dataclass(frozen=True)
class LogSwingCandidateRequest:
    ticker: str
    window_days: int
    entry_price: Decimal | None         # None = resolve from latest candle
    from_analysis: bool                 # True: run gate evaluation + trade plan
    preset: str | None                  # e.g. "foreign-bounce"
    with_regime: bool
    regime_universe: list[str]          # pre-resolved ticker list
    benchmark_ticker: str
    logged_at: date
    # Screen config (passed from SwingConfig — adapter owns _SC)
    tier1_broker_codes: frozenset[str]
    sector_breadth_enabled: bool
    sector_breadth_threshold: float
    sector_breadth_bonus_pts: float
    sector_breadth_min_tickers: int
    # Gate thresholds
    gate_min_score: float
    gate_min_vwap_discount_pct: float
    gate_required_trend: str
    gate_min_flow_ratio_pct: float
    gate_max_rsi: float
    watch_max_failed_gates: int
    # Multi-window pattern config
    multi_windows: tuple[int, ...] = (7, 30, 90)
    coiled_spring_min_score: float = 60.0
    coiled_spring_bb_pctile: float = 0.20
    # Trade plan (used only when from_analysis=True)
    take_profit_pct: Decimal = Decimal("5")
    stop_loss_pct: Decimal = Decimal("5")
    max_hold_days: int = 10


@dataclass(frozen=True)
class LogSwingCandidateResponse:
    ticker: str
    written: bool                       # False if duplicate
    classification: str | None          # ENTER / WATCH / AVOID (None when from_analysis=False)
    pattern: str | None
    regime: str | None
    entry_price: Decimal
    planned_stop: Decimal | None
    planned_target: Decimal | None
    failed_gates: tuple[str, ...]
    candidate_score: float | None       # None when ticker had no accumulation data


class LogSwingCandidateUseCase:
    def __init__(
        self,
        screen_use_case: "AccumulationScreenUseCase",
        journal_service: "AccumulationJournalService",
        market_repository: "MarketDataRepository",
        trade_journal_store: "TradeJournalStore | None" = None,
        regime_use_case: "MarketRegimeUseCase | None" = None,
    ) -> None:
        self._screen = screen_use_case
        self._journal = journal_service
        self._market = market_repository
        self._trade_store = trade_journal_store
        self._regime = regime_use_case

    def execute(self, request: LogSwingCandidateRequest) -> LogSwingCandidateResponse:
        ticker = request.ticker.upper()

        # 1. Single-ticker screen (threshold=0 — log regardless of score)
        screen_req = AccumulationScreenRequest(
            tickers=[ticker],
            window_days=request.window_days,
            min_score=0.0,
            min_net_buy_days=0,
            tier1_broker_codes=request.tier1_broker_codes,
            sector_breadth_enabled=request.sector_breadth_enabled,
            sector_breadth_threshold=request.sector_breadth_threshold,
            sector_breadth_bonus_pts=request.sector_breadth_bonus_pts,
            sector_breadth_min_tickers=request.sector_breadth_min_tickers,
        )
        response = self._screen.execute(screen_req)
        candidate: AccumulationCandidate | None = next(
            (c for c in response.candidates if c.ticker == ticker), None
        )

        # 2. Multi-window pattern
        pattern: str | None = None
        try:
            windows = list(request.multi_windows)
            multi = {
                w: self._screen.execute(AccumulationScreenRequest(
                    tickers=[ticker],
                    window_days=w,
                    min_score=0.0,
                    min_net_buy_days=0,
                    tier1_broker_codes=request.tier1_broker_codes,
                    sector_breadth_enabled=request.sector_breadth_enabled,
                    sector_breadth_threshold=request.sector_breadth_threshold,
                    sector_breadth_bonus_pts=request.sector_breadth_bonus_pts,
                    sector_breadth_min_tickers=request.sector_breadth_min_tickers,
                ))
                for w in windows
            }
            candidates_by_window = {
                w: next((c for c in resp.candidates if c.ticker == ticker), None)
                for w, resp in multi.items()
            }
            pattern = classify_multi_window_pattern(
                windows, candidates_by_window,
                request.coiled_spring_min_score,
                request.coiled_spring_bb_pctile,
            )
        except Exception:
            pass

        # 3. Resolve entry price
        resolved_entry: Decimal
        if request.entry_price is not None:
            resolved_entry = request.entry_price
        elif candidate is not None:
            try:
                candles = self._market.get_candles(
                    ticker,
                    start_date=request.logged_at.replace(month=1, day=1),
                    end_date=request.logged_at,
                )
                resolved_entry = candles[-1].close if candles else Decimal("0")
            except Exception:
                resolved_entry = Decimal("0")
        else:
            resolved_entry = Decimal("0")

        # 4. Gate evaluation + trade plan (only when from_analysis=True)
        classification: str | None = None
        failed_gates: tuple[str, ...] = ()
        planned_stop: Decimal | None = None
        planned_target: Decimal | None = None
        active_max_hold: int | None = None
        journal_preset: str | None = None

        if request.from_analysis:
            journal_preset = request.preset
            if candidate is None:
                classification = "AVOID"
                failed_gates = ("No accumulation/broker-flow candidate available",)
            else:
                classification, failed_gates = evaluate_foreign_bounce_gates(
                    candidate=candidate,
                    gate_min_score=request.gate_min_score,
                    gate_min_vwap_discount_pct=request.gate_min_vwap_discount_pct,
                    gate_required_trend=request.gate_required_trend,
                    gate_min_flow_ratio_pct=request.gate_min_flow_ratio_pct,
                    gate_max_rsi=request.gate_max_rsi,
                    watch_max_failed_gates=request.watch_max_failed_gates,
                )
            planned_stop, planned_target = compute_percent_plan(
                resolved_entry, request.stop_loss_pct, request.take_profit_pct
            )
            active_max_hold = request.max_hold_days

        # 5. Regime (only when from_analysis=True and regime_use_case wired)
        regime: str | None = None
        if request.from_analysis and request.with_regime and self._regime is not None:
            try:
                from src.application.use_case.market_regime import MarketRegimeRequest
                regime_response = self._regime.execute(MarketRegimeRequest(
                    universe=request.regime_universe,
                    benchmark_ticker=request.benchmark_ticker,
                    as_of_date=request.logged_at,
                ))
                regime = regime_response.label
            except Exception:
                pass

        # 6. CSV journal write
        planned_entry = resolved_entry if request.from_analysis else None
        written_count = self._journal.log_candidate(
            ticker=ticker,
            entry_price=resolved_entry,
            window_days=request.window_days,
            candidate=candidate,
            logged_at=request.logged_at,
            pattern=pattern,
            preset=journal_preset,
            classification=classification,
            failed_gates=failed_gates,
            regime=regime,
            planned_entry=planned_entry,
            planned_stop=planned_stop,
            planned_target=planned_target,
            max_hold_days=active_max_hold,
        )

        # 7. JSONL dual-write (only on new rows)
        if written_count > 0 and self._trade_store is not None:
            self._trade_store.append(self._build_trade_record(
                ticker=ticker,
                logged_at=request.logged_at,
                window_days=request.window_days,
                entry_price=resolved_entry,
                candidate=candidate,
                pattern=pattern,
                preset=journal_preset,
                decision=classification,
                failed_gates=failed_gates,
                regime=regime,
                planned_entry=planned_entry,
                planned_stop=planned_stop,
                planned_target=planned_target,
                max_hold_days=active_max_hold,
            ))

        return LogSwingCandidateResponse(
            ticker=ticker,
            written=written_count > 0,
            classification=classification,
            pattern=pattern,
            regime=regime,
            entry_price=resolved_entry,
            planned_stop=planned_stop,
            planned_target=planned_target,
            failed_gates=failed_gates,
            candidate_score=candidate.score if candidate else None,
        )

    @staticmethod
    def _build_trade_record(
        *,
        ticker: str,
        logged_at: date,
        window_days: int,
        entry_price: Decimal,
        candidate: "AccumulationCandidate | None",
        pattern: str | None,
        preset: str | None,
        decision: str | None,
        failed_gates: tuple[str, ...],
        regime: str | None,
        planned_entry: Decimal | None,
        planned_stop: Decimal | None,
        planned_target: Decimal | None,
        max_hold_days: int | None,
    ) -> dict:
        def _f(v: Decimal | None) -> float | None:
            return float(v) if v is not None else None

        return {
            "trade_type": "swing",
            "logged_at": str(logged_at),
            "ticker": ticker,
            "regime": regime,
            "trend": candidate.trend if candidate else None,
            "rsi": float(candidate.rsi) if candidate and candidate.rsi is not None else None,
            "decision": decision,
            "planned_entry": _f(planned_entry),
            "planned_stop": _f(planned_stop),
            "planned_target": _f(planned_target),
            "stop_pct": None,
            "entry_price": _f(entry_price),
            "window_days": window_days,
            "accum_score": candidate.score if candidate else 0.0,
            "accum_streak": candidate.consecutive_streak if candidate else 0,
            "flow_pct": float(candidate.avg_flow_ratio) if candidate and candidate.avg_flow_ratio is not None else None,
            "vwap_disc_pct": float(candidate.vwap_discount_pct) if candidate and candidate.vwap_discount_pct is not None else None,
            "bb_pctile": float(candidate.bb_width_pctile) if candidate and candidate.bb_width_pctile is not None else None,
            "pattern": pattern,
            "preset": preset,
            "failed_gates": list(failed_gates),
            "max_hold_days": max_hold_days,
            "actual_entry_price": None,
            "actual_exit_price": None,
            "outcome_result": None,
            "outcome_r": None,
            "outcome_notes": None,
            "actual_close_5d": None,
            "actual_close_10d": None,
            "actual_close_20d": None,
            "max_close_in_horizon": None,
            "min_close_in_horizon": None,
        }
