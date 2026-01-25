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
from src.domain.value_objects.sentiment import Sentiment

logger = logging.getLogger("ai_saham.sentiment")

# LLM Configuration
LLM_TIMEOUT_SECONDS = 10
LLM_MAX_TOKENS = 50

# System prompt for classification
SYSTEM_PROMPT = """You are a financial news sentiment classifier for Indonesian stocks.
Your task is to classify headlines as POSITIVE, NEUTRAL, or NEGATIVE.

Classification guidelines:
- POSITIVE: Good news about the company (profits up, expansion, strong performance)
- NEGATIVE: Bad news (losses, decline, regulatory issues, scandals)
- NEUTRAL: Factual news without clear positive/negative sentiment

Only respond with exactly one word: POSITIVE, NEUTRAL, or NEGATIVE.
No explanation or additional text."""

# User prompt template
USER_PROMPT = "Classify this headline: {headline}"


class AIClassifier:
    """AI-based headline classifier using LLM.

    Optional classifier that provides more nuanced sentiment analysis
    compared to keyword matching. Falls back to NEUTRAL on any error.

    Reuses the existing AI infrastructure (ExplainerFactory) for
    consistency and rate limiting.

    Usage:
        classifier = AIClassifier()  # Uses default provider
        classifier = AIClassifier(provider="ollama", model="llama3")

        sentiment = classifier.classify("BBCA laba naik 20%")
        # Returns Sentiment.POSITIVE
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
    ):
        """Initialize AI classifier.

        Args:
            provider: AI provider name (claude, openai, gemini, ollama)
                     If None, reads from AI_PROVIDER env var.
            model: Optional model override (mainly for Ollama)
        """
        self._provider = provider
        self._model = model
        self._client = None  # Lazy initialization

    @property
    def classifier_name(self) -> str:
        """Return classifier identifier."""
        provider = self._provider or os.getenv("AI_PROVIDER", "claude")
        return f"ai:{provider}"

    def classify(self, headline: str) -> Sentiment:
        """Classify headline using AI.

        Args:
            headline: The headline text to classify

        Returns:
            Sentiment classification. Returns NEUTRAL on any error.
        """
        try:
            response = self._call_ai(headline)
            return self._parse_response(response)
        except Exception as e:
            logger.warning(f"AI classification failed, defaulting to NEUTRAL: {e}")
            return Sentiment.NEUTRAL

    def classify_batch(self, headlines: list[str]) -> list[Sentiment]:
        """Classify multiple headlines.

        Note: Currently calls classify() for each headline.
        Could be optimized with batch prompts in the future.

        Args:
            headlines: List of headline texts to classify

        Returns:
            List of Sentiment classifications in same order
        """
        return [self.classify(h) for h in headlines]

    def _get_client(self):
        """Lazy initialize the AI client.

        Uses provider-specific client for efficiency.
        Falls back to default provider if not specified.
        """
        if self._client is not None:
            return self._client

        provider = (self._provider or os.getenv("AI_PROVIDER", "claude")).lower()

        if provider == "claude":
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

    def _call_ai(self, headline: str) -> str:
        """Call AI provider for classification.

        Args:
            headline: Headline text (truncated to 500 chars)

        Returns:
            Raw AI response text
        """
        # Truncate long headlines
        headline = headline[:500]
        user_prompt = USER_PROMPT.format(headline=headline)

        provider = (self._provider or os.getenv("AI_PROVIDER", "claude")).lower()

        start_time = time.time()
        logger.debug(f"AI classify request: provider={provider}")

        try:
            client = self._get_client()

            if provider == "claude":
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

    def _parse_response(self, response: str) -> Sentiment:
        """Parse AI response to Sentiment.

        Args:
            response: Raw AI response text

        Returns:
            Parsed Sentiment (defaults to NEUTRAL on ambiguous response)
        """
        response = response.strip().upper()

        if "POSITIVE" in response:
            return Sentiment.POSITIVE
        elif "NEGATIVE" in response:
            return Sentiment.NEGATIVE
        else:
            return Sentiment.NEUTRAL
