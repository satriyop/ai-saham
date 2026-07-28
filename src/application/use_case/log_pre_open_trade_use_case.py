"""LogPreOpenTradeUseCase — paper journal from immutable pre-open assess IDs.

Re-runs AssessPreOpenUseCase for the exact observation + opening snapshot,
then appends to the paper confirmation journal (CSV + trades.jsonl). Never
rereads live prices or confirmation sidecars.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.application.dto.assess_pre_open import (
    AssessPreOpenRequest,
    AssessPreOpenResult,
)
from src.application.services.pre_open_paper_journal import (
    PreOpenPaperJournalStore,
)
from src.application.use_case.assess_pre_open_use_case import AssessPreOpenUseCase
from src.domain.ports.trade_journal_store import TradeJournalStore
from src.domain.value_objects.pre_open_post_open_assessment import (
    PreOpenPaperJournalEntry,
)


@dataclass(frozen=True)
class LogPreOpenTradeRequest:
    observation_id: str
    opening_snapshot_id: str
    journal_path: Path


@dataclass(frozen=True)
class LogPreOpenTradeResponse:
    confirmed_at: str
    logged_count: int
    journal_path: Path
    duplicate: bool
    observation_id: str
    opening_snapshot_id: str
    analyze_result: AssessPreOpenResult


class LogPreOpenTradeUseCase:
    """Assess via immutable IDs, then write paper journal rows."""

    def __init__(
        self,
        analyze: AssessPreOpenUseCase,
        confirmation_store: PreOpenPaperJournalStore,
        trade_journal_store: TradeJournalStore | None = None,
    ) -> None:
        self._analyze = analyze
        self._confirmation_store = confirmation_store
        self._trade_journal_store = trade_journal_store

    def execute(self, request: LogPreOpenTradeRequest) -> LogPreOpenTradeResponse:
        if not request.observation_id or not request.opening_snapshot_id:
            raise ValueError(
                "Both observation_id and opening_snapshot_id are required for "
                "trade log --type pre-open"
            )
        result = self._analyze.execute(
            AssessPreOpenRequest(
                observation_id=request.observation_id,
                opening_snapshot_id=request.opening_snapshot_id,
            )
        )
        entries = [
            PreOpenPaperJournalEntry(
                confirmed_at=result.session_date,
                ticker=line.confirmation.ticker,
                decision=line.confirmation.decision.value,
                reason_codes=tuple(line.confirmation.reasons)
                + (
                    f"observation_id:{line.observation_id}",
                    f"opening_snapshot_id:{line.opening_snapshot_id or ''}",
                ),
                opening_price=line.confirmation.opening_price,
                planned_entry=line.confirmation.planned_entry,
                stop_loss_price=line.confirmation.stop_loss_price,
                stop_pct=line.confirmation.stop_pct,
                iev=line.confirmation.iev,
                trend=line.confirmation.trend,
                rsi=line.confirmation.rsi,
                gap_pct=line.confirmation.gap_pct,
                opening_broker_backing_tag=line.confirmation.opening_broker_backing_tag,
                fvwap_discount_pct=line.confirmation.fvwap_discount_pct,
            )
            for line in result.lines
        ]

        count = self._confirmation_store.append(entries)
        duplicate = count == 0
        if not duplicate and self._trade_journal_store is not None:
            for line, entry in zip(result.lines, entries, strict=True):
                self._trade_journal_store.append(
                    self._entry_to_record(
                        entry,
                        observation_id=line.observation_id,
                        opening_snapshot_id=line.opening_snapshot_id,
                        market_regime=result.market_regime,
                    )
                )

        return LogPreOpenTradeResponse(
            confirmed_at=result.session_date.isoformat(),
            logged_count=count,
            journal_path=request.journal_path,
            duplicate=duplicate,
            observation_id=request.observation_id,
            opening_snapshot_id=request.opening_snapshot_id,
            analyze_result=result,
        )

    @staticmethod
    def _f(v) -> float | None:
        if v is None:
            return None
        return float(v)

    @staticmethod
    def _entry_to_record(
        entry: PreOpenPaperJournalEntry,
        *,
        observation_id: str,
        opening_snapshot_id: str | None,
        market_regime: str | None,
    ) -> dict:
        return {
            "trade_type": "pre-open",
            "logged_at": str(entry.confirmed_at),
            "ticker": entry.ticker,
            "regime": market_regime,
            "trend": entry.trend,
            "rsi": LogPreOpenTradeUseCase._f(entry.rsi),
            "decision": entry.decision,
            "planned_entry": LogPreOpenTradeUseCase._f(entry.planned_entry),
            "planned_stop": LogPreOpenTradeUseCase._f(entry.stop_loss_price),
            "planned_target": None,
            "stop_pct": LogPreOpenTradeUseCase._f(entry.stop_pct),
            "iev": entry.iev,
            "gap_pct": LogPreOpenTradeUseCase._f(entry.gap_pct),
            "opening_broker_backing_tag": entry.opening_broker_backing_tag,
            "fvwap_discount_pct": LogPreOpenTradeUseCase._f(entry.fvwap_discount_pct),
            "opening_price": LogPreOpenTradeUseCase._f(entry.opening_price),
            "reason_codes": list(entry.reason_codes),
            "observation_id": observation_id,
            "opening_snapshot_id": opening_snapshot_id,
            "actual_entry_price": LogPreOpenTradeUseCase._f(entry.actual_entry_price),
            "actual_exit_price": LogPreOpenTradeUseCase._f(entry.actual_exit_price),
            "outcome_result": entry.outcome_result,
            "outcome_r": LogPreOpenTradeUseCase._f(entry.outcome_r),
            "outcome_notes": entry.outcome_notes,
        }
