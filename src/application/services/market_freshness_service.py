"""
Market data cache-freshness policy.

Derives the end-of-range cache tolerance used to decide whether cached
candle/broker data is still current, from an already-resolved
`EffectiveMarketSession`. Pure policy service — no repository, no
infrastructure imports, no adapter concerns.

Layer: Application
"""

from datetime import date

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.value_objects.trading_calendar import last_weekday


class MarketFreshnessService:
    """Derive cache tolerance from an already-resolved EffectiveMarketSession."""

    def resolve_reference_trading_day(
        self,
        effective_session: EffectiveMarketSession,
        today: date,
    ) -> date:
        """Effective session's latest completed session, falling back to the
        last weekday on first run (no cached session available yet)."""
        return effective_session.latest_completed_session or last_weekday(today)

    def end_tolerance_days(
        self,
        *,
        is_benchmark: bool,
        effective_session: EffectiveMarketSession,
        today: date,
    ) -> int:
        """
        How many calendar days old can cached data be and still be considered
        current? Derived from the resolved reference trading day.

        For the benchmark ticker itself, use the weekday fallback directly to
        break the circular dependency (benchmark candles can't use their own
        cached data/effective session to decide if they need updating).
        """
        if is_benchmark:
            last_trading = last_weekday(today)
        else:
            last_trading = self.resolve_reference_trading_day(effective_session, today)
        return max(0, (today - last_trading).days)
