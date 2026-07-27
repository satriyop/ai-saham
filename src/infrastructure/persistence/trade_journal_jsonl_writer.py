"""
TradeJournalJsonlWriter — JSON Lines implementation of TradeJournalStore.

One JSON object per line. Dedup keys (forward tokens):
  accum / swing (legacy): (trade_type, logged_at, ticker, window_days)
  pre-open / other:       (trade_type, logged_at, ticker)

Live dual-write uses trade_type "accum" | "pre-open".
Legacy rows may still use "swing" | "intraday" (raw history, not rewritten).

Converters remain for library/migration helpers (no product CLI).

Layer: Infrastructure
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.ports.trade_journal_store import TradeJournalStore

_ACCUM_TYPES = frozenset({"accum", "swing"})


def _dedup_key(r: dict) -> tuple:
    if r.get("trade_type") in _ACCUM_TYPES:
        return (r["trade_type"], r["logged_at"], r["ticker"], r.get("window_days"))
    return (r["trade_type"], r["logged_at"], r["ticker"])


def _f(v) -> float | None:
    """Safely convert Decimal/float/int to float, or return None."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def accumulation_entry_to_record(entry) -> dict:
    """Convert AccumulationJournalEntry → trade journal dict (library helper)."""
    return {
        "trade_type": "accum",
        "logged_at": str(entry.logged_at),
        "ticker": entry.ticker,
        "regime": entry.regime,
        "trend": entry.trend,
        "rsi": _f(entry.rsi),
        "decision": entry.setup_match,
        "planned_entry": _f(entry.planned_entry),
        "planned_stop": _f(entry.planned_stop),
        "planned_target": _f(entry.planned_target),
        "stop_pct": None,
        "entry_price": _f(entry.entry_price),
        "window_days": entry.window_days,
        "accum_score": entry.accum_score,
        "foreign_flow_buy_streak": entry.foreign_flow_buy_streak,
        "flow_pct": _f(entry.flow_pct),
        "vwap_disc_pct": _f(entry.vwap_disc_pct),
        "bb_pctile": _f(entry.bb_pctile),
        "pattern": entry.pattern,
        "setup": entry.setup,
        "failed_gates": list(entry.failed_gates),
        "max_hold_days": entry.max_hold_days,
        "actual_entry_price": None,
        "actual_exit_price": None,
        "outcome_result": None,
        "outcome_r": None,
        "outcome_notes": None,
        "actual_close_5d": _f(entry.actual_close_5d),
        "actual_close_10d": _f(entry.actual_close_10d),
        "actual_close_20d": _f(entry.actual_close_20d),
        "max_close_in_horizon": _f(entry.max_close_in_horizon),
        "min_close_in_horizon": _f(entry.min_close_in_horizon),
    }


def intraday_entry_to_record(entry) -> dict:
    """Convert PreOpenPaperJournalEntry → trade journal dict (library helper)."""
    return {
        "trade_type": "pre-open",
        "logged_at": str(entry.confirmed_at),
        "ticker": entry.ticker,
        "regime": None,
        "trend": entry.trend,
        "rsi": _f(entry.rsi),
        "decision": entry.decision,
        "planned_entry": _f(entry.planned_entry),
        "planned_stop": _f(entry.stop_loss_price),
        "planned_target": None,
        "stop_pct": _f(entry.stop_pct),
        "iev": entry.iev,
        "gap_pct": _f(entry.gap_pct),
        "opening_broker_backing_tag": entry.opening_broker_backing_tag,
        "fvwap_discount_pct": _f(entry.fvwap_discount_pct),
        "opening_price": _f(entry.opening_price),
        "reason_codes": list(entry.reason_codes),
        "actual_entry_price": _f(entry.actual_entry_price),
        "actual_exit_price": _f(entry.actual_exit_price),
        "outcome_result": entry.outcome_result,
        "outcome_r": _f(entry.outcome_r),
        "outcome_notes": entry.outcome_notes,
    }


def swing_candidate_to_record(
    *,
    ticker: str,
    logged_at: date,
    window_days: int,
    entry_price: Decimal,
    candidate,
    pattern: str | None,
    setup: str | None,
    setup_match: str | None,
    failed_gates: tuple[str, ...],
    regime: str | None,
    planned_entry: Decimal | None,
    planned_stop: Decimal | None,
    planned_target: Decimal | None,
    max_hold_days: int | None,
) -> dict:
    """Build an accum paper trade record from live screen data (used at log time)."""
    return {
        "trade_type": "accum",
        "logged_at": str(logged_at),
        "ticker": ticker,
        "regime": regime,
        "trend": candidate.trend if candidate else None,
        "rsi": float(candidate.rsi) if candidate and candidate.rsi is not None else None,
        "decision": setup_match,
        "planned_entry": _f(planned_entry),
        "planned_stop": _f(planned_stop),
        "planned_target": _f(planned_target),
        "stop_pct": None,
        "entry_price": _f(entry_price),
        "window_days": window_days,
        "accum_score": candidate.accum_score if candidate else None,
        "foreign_flow_buy_streak": candidate.consecutive_streak if candidate else None,
        "flow_pct": (
            float(candidate.avg_flow_ratio)
            if candidate and candidate.avg_flow_ratio is not None
            else None
        ),
        "vwap_disc_pct": (
            float(candidate.vwap_discount_pct)
            if candidate and candidate.vwap_discount_pct is not None
            else None
        ),
        "bb_pctile": (
            float(candidate.bb_width_pctile)
            if candidate and candidate.bb_width_pctile is not None
            else None
        ),
        "pattern": pattern,
        "setup": setup,
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


class TradeJournalJsonlWriter(TradeJournalStore):
    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, record: dict) -> bool:
        existing_keys = {_dedup_key(r) for r in self.read_all()}
        key = _dedup_key(record)
        if key in existing_keys:
            return False
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        return True

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        rows: list[dict] = []
        with self._path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        rows.sort(key=lambda r: (r.get("logged_at", ""), r.get("ticker", "")))
        return rows

    def update(self, record: dict) -> bool:
        if not self._path.exists():
            return False
        key = _dedup_key(record)
        rows = self.read_all()
        found = False
        for i, row in enumerate(rows):
            if _dedup_key(row) == key:
                rows[i] = record
                found = True
                break
        if not found:
            return False
        with self._path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, default=str) + "\n")
        return True
