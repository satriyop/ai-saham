"""
Swing analysis data freshness helpers.

Consumes a canonically resolved `EffectiveMarketSession` (see
`effective_market_session_resolver.py`) for the expected latest data date
instead of computing it independently with weekday arithmetic — the
weekday-only `expected_weekday_data_date`/`weekday_session_lag` helpers this
module previously owned have been removed.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass(frozen=True)
class SwingDataFreshness:
    """Cached source data dates used by a swing analysis run."""

    as_of_date: date
    candle_start: date | None
    candle_end: date | None
    broker_start: date | None
    broker_end: date | None
    warnings: tuple[str, ...]
    refresh_actions: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "candles_from": self.candle_start.isoformat() if self.candle_start else None,
            "candles_through": self.candle_end.isoformat() if self.candle_end else None,
            "broker_flow_from": self.broker_start.isoformat() if self.broker_start else None,
            "broker_flow_through": self.broker_end.isoformat() if self.broker_end else None,
            "refresh_actions": list(self.refresh_actions),
            "warnings": list(self.warnings),
        }


def _stale_warning(label: str, source_date: date, expected_date: date) -> str:
    return f"Latest {label} ({source_date}) is stale versus expected data date ({expected_date})."


def build_swing_data_freshness(
    ticker: str,
    effective_session: EffectiveMarketSession,
    market_repo: MarketDataRepository,
    broker_repo: BrokerDataRepository,
    refresh_actions: tuple[str, ...] = (),
) -> SwingDataFreshness:
    candle_range = market_repo.get_date_range(ticker)
    broker_range = broker_repo.get_date_range(ticker)
    candle_start, candle_end = candle_range if candle_range else (None, None)
    broker_start, broker_end = broker_range if broker_range else (None, None)

    expected_date = effective_session.latest_completed_session

    warnings: list[str] = []
    if candle_end is None:
        warnings.append(f"No cached candle data for {ticker}.")
    elif expected_date is not None and candle_end < expected_date:
        warnings.append(_stale_warning("candle", candle_end, expected_date))

    if broker_end is None:
        warnings.append(f"No cached broker flow data for {ticker}.")
    elif expected_date is not None and broker_end < expected_date:
        warnings.append(_stale_warning("broker flow", broker_end, expected_date))

    if expected_date is None and (candle_end is not None or broker_end is not None):
        warnings.append(
            "Expected data date is unknown because the effective market "
            "session could not resolve a latest completed session."
        )

    if candle_end and broker_end and candle_end != broker_end:
        warnings.append(f"Candle date ({candle_end}) and broker flow date ({broker_end}) differ.")
    for action in refresh_actions:
        if "ERR:" in action:
            warnings.append(f"Refresh issue: {action}")

    as_of_date = (
        effective_session.analysis_as_of
        or effective_session.latest_completed_session
        or effective_session.decision_at.date()
    )

    return SwingDataFreshness(
        as_of_date=as_of_date,
        candle_start=candle_start,
        candle_end=candle_end,
        broker_start=broker_start,
        broker_end=broker_end,
        warnings=tuple(warnings),
        refresh_actions=refresh_actions,
    )
