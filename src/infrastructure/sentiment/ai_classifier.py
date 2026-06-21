"""
AI-based headline classifier.

Uses LLM to classify headline sentiment. Optional enhancement
over the default keyword classifier.

Layer: Infrastructure
"""

import logging
import os
import time

from src.domain.ports.headline_classifier import HeadlineClassifierError
from src.domain.value_objects.sentiment import CatalystType, Classification, Sentiment
from src.infrastructure.config.app_config import APP_CFG

logger = logging.getLogger("ai_saham.sentiment")

_DEFAULT_AI_PROVIDER: str = APP_CFG.ai.provider

# LLM Configuration
LLM_TIMEOUT_SECONDS = 10
LLM_MAX_TOKENS = 60

# System prompt for classification
SYSTEM_PROMPT = """You are a financial news sentiment and catalyst classifier for Indonesian stocks.
Your task is to classify headlines as follows:

1. Sentiment: POSITIVE, NEUTRAL, or NEGATIVE.
2. Catalyst: EARNINGS, CORP_ACTION, REGULATORY, MACRO, GOVERNANCE, RUMOR, or GENERAL.

Classification guidelines for Catalysts:
- EARNINGS: Quarterly reports, profit projections, dividend news.
- CORP_ACTION: Stock splits, rights issues, buybacks, mergers, acquisitions.
- REGULATORY: Government policy, export bans, OJK/IDX mandates, legal cases.
- MACRO: Interest rates, global markets, commodity prices (Coal, Nickel, etc.).
- GOVERNANCE: Management changes, scandals, audits, ownership shifts.
- RUMOR: Unverified news, market gossip, speculative whispers.
- GENERAL: News that doesn't fit specific categories above.

Only respond in the format: SENTIMENT | CATALYST
Example: POSITIVE | EARNINGS
Example: NEGATIVE | RUMOR
No explanation or additional text."""

# User prompt template
USER_PROMPT = "Classify the sentiment of this headline STRICTLY in relation to the company represented by ticker '{ticker}'.\n\nHeadline: {headline}"


class AIClassifier:
    """AI-based headline classifier using LLM.

    Optional classifier that provides nuanced sentiment and catalyst
    analysis compared to keyword matching. Falls back to NEUTRAL|GENERAL on any error.

    Reuses existing AI infrastructure for consistency and rate limiting.

    Usage:
        classifier = AIClassifier()
        result = classifier.classify("BBCA", "BBCA laba naik 20%")
        # Returns Classification(sentiment=Sentiment.POSITIVE, catalyst=CatalystType.EARNINGS)
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
    ):
        """Initialize AI classifier.

        Args:
            provider: AI provider name (deepseek, claude, openai, gemini, ollama)
                     If None, reads from AI_PROVIDER env var.
            model: Optional model override
        """
        self._provider = provider
        self._model = model
        self._client = None  # Lazy initialization

    @property
    def classifier_name(self) -> str:
        """Return classifier identifier."""
        provider = self._provider or os.getenv("AI_PROVIDER", _DEFAULT_AI_PROVIDER)
        return f"ai:{provider}"

    def classify(self, ticker: str, headline: str) -> Classification:
        """Classify headline using AI.

        Args:
            ticker: The stock ticker to evaluate the headline against
            headline: The headline text to classify

        Returns:
            Classification result. Returns NEUTRAL|GENERAL on any error.
        """
        try:
            response = self._call_ai(ticker, headline)
            return self._parse_response(response)
        except Exception as e:
            logger.warning(f"AI classification failed, defaulting to NEUTRAL|GENERAL: {e}")
            return Classification(Sentiment.NEUTRAL, CatalystType.GENERAL)

    def classify_batch(self, ticker: str, headlines: list[str]) -> list[Classification]:
        """Classify multiple headlines.

        Args:
            ticker: The stock ticker
            headlines: List of headline texts to classify

        Returns:
            List of Classification results in same order
        """
        return [self.classify(ticker, h) for h in headlines]


    def _get_client(self):
        """Lazy initialize the AI client.

        Uses provider-specific client for efficiency.
        Falls back to default provider if not specified.
        """
        if self._client is not None:
            return self._client

        provider = (self._provider or os.getenv("AI_PROVIDER", _DEFAULT_AI_PROVIDER)).lower()

        if provider == "deepseek":
            self._client = self._create_deepseek_client()
        elif provider == "claude":
            self._client = self._create_claude_client()
        elif provider == "openai":
            self._client = self._create_openai_client()
        elif provider == "gemini":
            self._client = self._create_gemini_client()
        elif provider == "ollama":
            self._client = self._create_ollama_client()
        else:
            raise HeadlineClassifierError(f"Unsupported AI provider: {provider}")

        return self._client

    def _create_deepseek_client(self):
        """Create DeepSeek client (using OpenAI SDK)."""
        try:
            import openai

            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise HeadlineClassifierError("DEEPSEEK_API_KEY not set")
            # DeepSeek uses OpenAI-compatible API
            return openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
                timeout=LLM_TIMEOUT_SECONDS
            )
        except ImportError:
            raise HeadlineClassifierError("openai package not installed (required for DeepSeek)")

    def _create_claude_client(self):
        """Create Claude client."""
        try:
            import anthropic

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise HeadlineClassifierError("ANTHROPIC_API_KEY not set")
            return anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
        except ImportError:
            raise HeadlineClassifierError("anthropic package not installed")

    def _create_openai_client(self):
        """Create OpenAI client."""
        try:
            import openai

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise HeadlineClassifierError("OPENAI_API_KEY not set")
            return openai.OpenAI(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
        except ImportError:
            raise HeadlineClassifierError("openai package not installed")

    def _create_gemini_client(self):
        """Create Gemini client."""
        try:
            import google.generativeai as genai

            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise HeadlineClassifierError("GOOGLE_API_KEY not set")
            genai.configure(api_key=api_key)
            model = self._model or "gemini-1.5-flash"
            return genai.GenerativeModel(model)
        except ImportError:
            raise HeadlineClassifierError("google-generativeai package not installed")

    def _create_ollama_client(self):
        """Create Ollama client (returns dict with config)."""
        try:
            import ollama

            return {
                "client": ollama,
                "model": self._model or os.getenv("OLLAMA_MODEL", "llama3.2"),
            }
        except ImportError:
            raise HeadlineClassifierError("ollama package not installed")

    def _call_ai(self, ticker: str, headline: str) -> str:
        """Call AI provider for classification.

        Args:
            ticker: Stock ticker symbol
            headline: Headline text (truncated to 500 chars)

        Returns:
            Raw AI response text
        """
        # Truncate long headlines
        headline = headline[:500]
        user_prompt = USER_PROMPT.format(ticker=ticker, headline=headline)

        provider = (self._provider or os.getenv("AI_PROVIDER", _DEFAULT_AI_PROVIDER)).lower()

        start_time = time.time()
        logger.debug(f"AI classify request: provider={provider}")

        try:
            client = self._get_client()

            if provider == "deepseek":
                response = self._call_deepseek(client, user_prompt)
            elif provider == "claude":
                response = self._call_claude(client, user_prompt)
            elif provider == "openai":
                response = self._call_openai(client, user_prompt)
            elif provider == "gemini":
                response = self._call_gemini(client, user_prompt)
            elif provider == "ollama":
                response = self._call_ollama(client, user_prompt)
            else:
                raise HeadlineClassifierError(f"Unsupported provider: {provider}")

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"AI classify response: time={elapsed_ms}ms")

            return response

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"AI classify error after {elapsed_ms}ms: {e}")
            raise

    def _call_deepseek(self, client, user_prompt: str) -> str:
        """Call DeepSeek API."""
        response = client.chat.completions.create(
            model=self._model or "deepseek-chat",  # Default model
            max_tokens=LLM_MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def _call_claude(self, client, user_prompt: str) -> str:
        """Call Claude API."""
        response = client.messages.create(
            model="claude-3-haiku-20240307",  # Fast model for classification
            max_tokens=LLM_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    def _call_openai(self, client, user_prompt: str) -> str:
        """Call OpenAI API."""
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast model for classification
            max_tokens=LLM_MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def _call_gemini(self, client, user_prompt: str) -> str:
        """Call Gemini API."""
        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
        response = client.generate_content(full_prompt)
        return response.text

    def _call_ollama(self, config: dict, user_prompt: str) -> str:
        """Call Ollama local API."""
        client = config["client"]
        model = config["model"]
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response["message"]["content"]

    def _parse_response(self, response: str) -> Classification:
        """Parse AI response to Classification.

        Args:
            response: Raw AI response text (expected: SENTIMENT | CATALYST)

        Returns:
            Parsed Classification (defaults to NEUTRAL|GENERAL on ambiguity)
        """
        response = response.strip().upper()

        sentiment = Sentiment.NEUTRAL
        if "POSITIVE" in response:
            sentiment = Sentiment.POSITIVE
        elif "NEGATIVE" in response:
            sentiment = Sentiment.NEGATIVE

        catalyst = CatalystType.GENERAL
        if "|" in response:
            cat_part = response.split("|")[1].strip()
            for ct in CatalystType:
                if ct.name in cat_part:
                    catalyst = ct
                    break

        return Classification(sentiment=sentiment, catalyst=catalyst)
