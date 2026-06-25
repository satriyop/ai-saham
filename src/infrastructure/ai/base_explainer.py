"""
Base explainer with shared logic for all LLM adapters.

Contains common prompt templates, constants, sanitization, and error handling.

Layer: Infrastructure
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment

logger = logging.getLogger("ai_saham.ai")

# LLM Hardening Constants
LLM_TIMEOUT_SECONDS = 10
LLM_MAX_RETRIES = 1
LLM_MAX_TOKENS = 300

# System prompt for all LLM providers
SYSTEM_PROMPT = """You are a stock analysis assistant explaining technical analysis results \
to retail investors.

Your role is to EXPLAIN results, not generate or modify them. The risk assessment has \
already been computed by a deterministic rule engine.

Guidelines:
- Explain what the indicators mean in plain language
- Explain why the risk level was assigned
- Do NOT provide trading advice or recommendations
- Do NOT suggest buying or selling
- Keep explanations concise (2-3 paragraphs)
- Use simple language avoiding jargon"""

# User prompt template
USER_PROMPT_TEMPLATE = """Explain this risk assessment to a beginner investor:

Ticker: {ticker}
Date: {date}
Signal Sensitivity: {sensitivity}

Technical Indicators:
- SMA(20): {sma}
- EMA(20): {ema}
- RSI(14): {rsi}

Assessment Result:
- Risk Level: {risk_level}
- Confidence: {confidence}/100

Rule Engine Rationale:
{rationale}

Provide a clear, educational explanation of what this means."""


@dataclass(frozen=True)
class SanitizedInput:
    """LLM-safe representation of assessment data.

    All fields are strings to prevent serialization issues.
    """

    ticker: str
    date: str
    sensitivity: str
    risk_level: str
    confidence: str
    sma: str
    ema: str
    rsi: str
    rationale: str


def sanitize_for_llm(
    ticker: str,
    assessment: RiskAssessment,
    snapshot: IndicatorSnapshot,
) -> SanitizedInput:
    """Extract and sanitize data for LLM consumption.

    Converts all values to strings to prevent:
    - Decimal serialization issues
    - Date object serialization issues
    - Accidental data leakage

    Args:
        ticker: Stock ticker symbol
        assessment: The risk assessment result
        snapshot: The indicator snapshot

    Returns:
        SanitizedInput with string-only fields
    """
    return SanitizedInput(
        ticker=ticker,
        date=str(snapshot.date),
        sensitivity=assessment.sensitivity_name,
        risk_level=assessment.risk_level_name,
        confidence=str(assessment.confidence),
        sma=f"{snapshot.sma:,.2f}",
        ema=f"{snapshot.ema:,.2f}",
        rsi=f"{snapshot.rsi:.2f}",
        rationale="\n".join(f"  - {r}" for r in assessment.rationale),
    )


def build_user_prompt(sanitized: SanitizedInput) -> str:
    """Build the user prompt from sanitized input."""
    return USER_PROMPT_TEMPLATE.format(
        ticker=sanitized.ticker,
        date=sanitized.date,
        sensitivity=sanitized.sensitivity,
        sma=sanitized.sma,
        ema=sanitized.ema,
        rsi=sanitized.rsi,
        risk_level=sanitized.risk_level,
        confidence=sanitized.confidence,
        rationale=sanitized.rationale,
    )


class BaseExplainer(ABC):
    """Abstract base class for LLM explainer adapters.

    Provides shared logic for prompt building, sanitization, and logging.
    Subclasses implement the provider-specific API call.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name for logging."""
        ...

    def explain_assessment(
        self,
        ticker: str,
        assessment: RiskAssessment,
        snapshot: IndicatorSnapshot,
    ) -> str:
        """Generate explanation using the LLM provider.

        This method handles common logic (sanitization, prompt building,
        logging) and delegates to _call_llm for provider-specific API calls.
        """
        import time

        # Sanitize input
        sanitized = sanitize_for_llm(ticker, assessment, snapshot)
        user_prompt = build_user_prompt(sanitized)

        logger.info(f"AI request: provider={self.provider_name}, ticker={ticker}")

        start_time = time.time()
        try:
            explanation, token_count = self._call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"AI response: tokens={token_count}, time={elapsed_ms}ms")
            return explanation

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"AI error: {type(e).__name__}: {e}")
            raise

    @abstractmethod
    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, int]:
        """Make the actual LLM API call.

        Args:
            system_prompt: The system prompt
            user_prompt: The user prompt

        Returns:
            Tuple of (explanation_text, total_token_count)

        Raises:
            ExplainerError subclass on failure
        """
        ...
