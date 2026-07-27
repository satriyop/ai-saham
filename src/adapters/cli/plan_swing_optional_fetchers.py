"""
Optional refresh/sentiment fetchers for the saham analyze swing workflow.

Layer: Adapter

Owns provider-refresh wiring and sentiment fetch/noise-suppression so the
top-level workflow factory does not own optional-evidence fetch mechanics.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from src.application.services.swing_data_refresh import refresh_swing_data
from src.application.use_case.fetch_sentiment_use_case import (
    FetchSentimentRequest,
    FetchSentimentUseCase,
)
from src.infrastructure.config.analyze_swing_config import AnalyzeSwingConfig
from src.infrastructure.sentiment import SentimentFactory


def auto_refresh_swing_data(
    *,
    ticker: str,
    db_path: Path,
    force_refresh: bool,
    analyze_config: AnalyzeSwingConfig,
) -> tuple[str, ...]:
    from src.adapters.cli.fetch_market_provider_factory import create_broker_provider
    from src.infrastructure.composition.fetch_market.fetch_market_broker_refresh import fetch_broker
    from src.infrastructure.composition.fetch_market.fetch_market_candle_refresh import (
        fetch_candles,
    )

    return refresh_swing_data(
        ticker=ticker,
        db_path=db_path,
        force_refresh=force_refresh,
        market_refresh_days=analyze_config.market_refresh_days,
        broker_refresh_days=analyze_config.broker_refresh_days,
        fetch_candles=fetch_candles,
        create_broker_provider=create_broker_provider,
        fetch_broker=fetch_broker,
    )


@contextmanager
def _quiet_sentiment_fetch(enabled: bool):
    """Suppress optional sentiment provider noise in composite swing output."""
    if not enabled:
        with nullcontext():
            yield
        return

    previous_disable = logging.root.manager.disable
    sink = StringIO()
    try:
        logging.disable(logging.CRITICAL)
        with redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous_disable)


def fetch_swing_sentiment(
    *,
    ticker: str,
    sentiment_verbose: bool,
    analyze_config: AnalyzeSwingConfig,
):
    """Fetch optional sentiment context without leaking provider noise by default."""
    try:
        with _quiet_sentiment_fetch(enabled=not sentiment_verbose):
            news_provider = SentimentFactory.create_news_provider()
            classifier = SentimentFactory.create_classifier(use_ai=False)
            sent_uc = FetchSentimentUseCase(
                news_provider=news_provider,
                classifier=classifier,
            )
            response = sent_uc.execute(
                FetchSentimentRequest(
                    ticker=ticker,
                    max_headlines=analyze_config.sentiment_max_headlines,
                    days=analyze_config.sentiment_days,
                )
            )
        return response, response.warning
    except Exception as exc:
        if sentiment_verbose:
            return None, f"Sentiment fetch failed: {exc}"
        return None, "News unavailable (provider fetch failed)."
