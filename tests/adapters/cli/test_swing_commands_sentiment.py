"""Sentiment provider noise tests for swing commands."""

import logging
import sys

from src.adapters.cli.analyze_swing_commands import _fetch_swing_sentiment


class NoisyNewsProvider:
    provider_name = "noisy"

    def fetch_headlines(self, ticker: str, max_headlines: int = 20, days: int = 3):
        print("RAW_SENTIMENT_STDOUT")
        print("RAW_SENTIMENT_STDERR", file=sys.stderr)
        logging.getLogger("ai_saham.sentiment").warning("RAW_SENTIMENT_LOG")
        raise RuntimeError("RAW_SENTIMENT_EXCEPTION")


def test_fetch_swing_sentiment_suppresses_provider_noise_by_default(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_workflow_factory.SentimentFactory.create_news_provider",
        lambda: NoisyNewsProvider(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_workflow_factory.SentimentFactory.create_classifier",
        lambda use_ai=False: object(),
    )

    response, warning = _fetch_swing_sentiment("BBCA", sentiment_verbose=False)

    captured = capsys.readouterr()
    assert response is None
    assert warning == "News unavailable (provider fetch failed)."
    assert "RAW_SENTIMENT" not in captured.out
    assert "RAW_SENTIMENT" not in captured.err


def test_fetch_swing_sentiment_verbose_keeps_provider_details(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_workflow_factory.SentimentFactory.create_news_provider",
        lambda: NoisyNewsProvider(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_workflow_factory.SentimentFactory.create_classifier",
        lambda use_ai=False: object(),
    )

    response, warning = _fetch_swing_sentiment("BBCA", sentiment_verbose=True)

    captured = capsys.readouterr()
    assert response is None
    assert warning == "Sentiment fetch failed: RAW_SENTIMENT_EXCEPTION"
    assert "RAW_SENTIMENT_STDOUT" in captured.out
    assert "RAW_SENTIMENT_STDERR" in captured.err
