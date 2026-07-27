"""
Tests for sentiment audit use case.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.use_case.audit_sentiment_use_case import (
    AuditSentimentRequest,
    AuditSentimentUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.sentiment_repository import SentimentLog
from src.domain.value_objects.sentiment import CatalystType, Sentiment


@pytest.fixture
def mock_sentiment_repo():
    """Mock for SentimentRepository."""
    return MagicMock()


@pytest.fixture
def mock_market_repo():
    """Mock for MarketDataRepository."""
    return MagicMock()


class TestAuditSentimentUseCase:
    """Test AuditSentimentUseCase functionality."""

    def test_audit_logs_successfully(self, mock_sentiment_repo, mock_market_repo):
        """Use case should compute delta and save audits."""
        # 1. Setup unaudited logs
        log_date = date(2026, 6, 1)
        log = SentimentLog(
            id=101,
            date=log_date,
            ticker="BBCA",
            sentiment=Sentiment.POSITIVE,
            catalyst=CatalystType.EARNINGS,
            score=0.8,
        )
        mock_sentiment_repo.get_unaudited_logs.return_value = [log]
        mock_sentiment_repo.get_stats.return_value = {"audited_logs": 1}

        # 2. Setup market data
        # Index 0: log date, Index 5: 5 days later
        candles = [
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 1),
                open=9000,
                high=9100,
                low=8900,
                close=9000,
                volume=1000,
            ),
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 2),
                open=9100,
                high=9200,
                low=9000,
                close=9100,
                volume=1000,
            ),
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 3),
                open=9200,
                high=9300,
                low=9100,
                close=9200,
                volume=1000,
            ),
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 4),
                open=9300,
                high=9400,
                low=9200,
                close=9300,
                volume=1000,
            ),
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 5),
                open=9400,
                high=9500,
                low=9300,
                close=9400,
                volume=1000,
            ),
            Candle(
                ticker="BBCA",
                date=date(2026, 6, 6),
                open=9900,
                high=10000,
                low=9800,
                close=9900,
                volume=1000,
            ),  # 5th index
        ]
        mock_market_repo.get_candles.return_value = candles

        # 3. Execute
        use_case = AuditSentimentUseCase(
            sentiment_repo=mock_sentiment_repo, market_repo=mock_market_repo
        )
        request = AuditSentimentRequest(days_ago=[5])
        response = use_case.execute(request)

        # 4. Verify
        assert response.logs_audited == 1
        assert response.audits_saved == 1

        # Price delta: (9900 - 9000) / 9000 = 10%
        args, _ = mock_sentiment_repo.save_audit.call_args
        audit = args[0]
        assert audit.log_id == 101
        assert audit.days_after == 5
        assert audit.price_delta_pct == Decimal("10.00")

    def test_handles_insufficient_market_data(self, mock_sentiment_repo, mock_market_repo):
        """Use case should skip audit if market data is too short."""
        log = SentimentLog(
            id=1,
            date=date(2026, 6, 1),
            ticker="X",
            sentiment=Sentiment.NEUTRAL,
            catalyst=CatalystType.GENERAL,
            score=1.0,
        )
        mock_sentiment_repo.get_unaudited_logs.return_value = [log]
        mock_market_repo.get_candles.return_value = [
            Candle(
                ticker="X", date=date(2026, 6, 1), open=100, high=100, low=100, close=100, volume=0
            )
        ]

        use_case = AuditSentimentUseCase(
            sentiment_repo=mock_sentiment_repo, market_repo=mock_market_repo
        )
        response = use_case.execute(AuditSentimentRequest(days_ago=[5]))

        assert response.audits_saved == 0
        mock_sentiment_repo.save_audit.assert_not_called()
