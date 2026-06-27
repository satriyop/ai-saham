"""
Audit sentiment use case.

Compares past sentiment predictions against actual price moves
after 1, 3, and 5 trading days.

Layer: Application (Use Case)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.sentiment_repository import SentimentAudit, SentimentRepository


@dataclass
class AuditSentimentRequest:
    """Request DTO for auditing sentiment logs."""

    days_ago: list[int] = None  # Horizons to audit, e.g., [1, 3, 5]


@dataclass
class AuditSentimentResponse:
    """Response DTO for sentiment audit."""

    logs_audited: int
    audits_saved: int
    stats: dict


class AuditSentimentUseCase:
    """Orchestrates the auditing of past sentiment predictions.

    Finds sentiment logs that are old enough to have actual price
    outcomes and records the delta.
    """

    def __init__(
        self,
        sentiment_repo: SentimentRepository,
        market_repo: MarketDataRepository,
    ):
        """Initialize use case with dependencies.

        Args:
            sentiment_repo: Repository for sentiment logs and audits
            market_repo: Repository for historical price data
        """
        self._sentiment_repo = sentiment_repo
        self._market_repo = market_repo

    def execute(self, request: AuditSentimentRequest) -> AuditSentimentResponse:
        """Execute auditing process.

        Args:
            request: Audit parameters

        Returns:
            Summary of audits performed
        """
        horizons = request.days_ago or [1, 3, 5]
        total_logs = 0
        total_audits = 0

        for horizon in horizons:
            # Find logs that are at least 'horizon' days old and lack this audit
            logs = self._sentiment_repo.get_unaudited_logs(days_ago=horizon)
            total_logs += len(logs)

            for log in logs:
                delta = self._compute_price_delta(log.ticker, log.date, horizon)
                if delta is not None:
                    self._sentiment_repo.save_audit(
                        SentimentAudit(
                            log_id=log.id,
                            days_after=horizon,
                            price_delta_pct=delta,
                            audited_at=date.today()
                        )
                    )
                    total_audits += 1

        stats = self._sentiment_repo.get_stats()

        return AuditSentimentResponse(
            logs_audited=total_logs,
            audits_saved=total_audits,
            stats=stats
        )

    def _compute_price_delta(self, ticker: str, start_date: date, days_after: int) -> Optional[Decimal]:
        """Compute actual price delta over a trading window.

        Args:
            ticker: Stock ticker
            start_date: The date of the news/sentiment
            days_after: The horizon in days

        Returns:
            Price delta percentage (Decimal) or None if insufficient data
        """
        candles = self._market_repo.get_candles(ticker.upper())

        if not candles:
            return None

        # Filter candles for start date and subsequent days
        relevant = [c for c in candles if c.date >= start_date]
        if not relevant:
            return None

        # Start price is the close on the start_date (or the next available day)
        start_candle = relevant[0]
        start_price = start_candle.close

        # Target index based on trading days
        if len(relevant) <= days_after:
            return None

        end_candle = relevant[days_after]
        end_price = end_candle.close

        if start_price == 0:
            return None

        delta = Decimal(str((end_price - start_price) / start_price * 100))
        return delta.quantize(Decimal("0.01"))
