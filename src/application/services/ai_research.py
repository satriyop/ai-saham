"""
AI research service for ticker-level pre-open analysis.

Provides a lightweight interface for asking an AI provider an open-ended
research question about a stock ticker. Used by the pre-open screener
to generate a brief human-readable summary per candidate.

Layer: Application (thin wrapper — no domain logic)
Mode: AI Mode ON
"""

from __future__ import annotations

import os
from typing import Protocol


RESEARCH_SYSTEM_PROMPT = """\
You are a concise stock research assistant for Indonesia's IDX market.
Summarize key pre-open signals for a given ticker in plain language.
Do NOT recommend buying or selling. Focus on observable facts: recent
price trend, known corporate events, and any notable affiliate/parent
tickers that are trending. Keep it under 3 sentences."""

RESEARCH_USER_PROMPT = """\
Pre-open research for IDX ticker: {ticker}
Date: {date}
Summarize: 1) Recent price trend 2) Any notable news/events 3) Affiliated companies trend.
"""


class TickerResearcher(Protocol):
    """Protocol for any AI-backed ticker researcher."""

    def research(self, ticker: str) -> str:
        """Return a 1-3 sentence research summary for ticker."""
        ...


class ClaudeTickerResearcher:
    """Ticker researcher backed by Claude API.

    Shares the same pattern as ClaudeExplainer but is optimised for
    short free-form research queries, not structured assessment explanations.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 200,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ValueError(
                "No API key for Claude (set ANTHROPIC_API_KEY environment variable)"
            )
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout

    def research(self, ticker: str) -> str:
        """Call Claude to produce a brief pre-open summary for ticker."""
        try:
            import anthropic
        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            )

        from datetime import date

        client = anthropic.Anthropic(api_key=self._api_key, timeout=self._timeout)
        message = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=RESEARCH_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": RESEARCH_USER_PROMPT.format(
                        ticker=ticker, date=date.today()
                    ),
                }
            ],
        )
        return message.content[0].text if message.content else ""
