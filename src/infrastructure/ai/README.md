# AI Infrastructure Layer

This module contains AI adapter implementations for the AI Saham analysis engine.

## Philosophy: AI as an Adapter

Even in "full AI mode", AI remains:
- **An adapter** - Implements domain ports, can be swapped
- **Swappable** - Claude → OpenAI → Ollama → Mock
- **Bypassable** - System works 100% without AI
- **Traceable** - All AI outputs are logged and attributed

This is how we avoid violating hexagonal architecture when using AI.

---

## Components

### 1. AI Explainers

Translate risk assessments into human-readable explanations.

| Adapter | File | Provider | Requires |
|---------|------|----------|----------|
| Claude | `claude_explainer.py` | Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `openai_explainer.py` | OpenAI | `OPENAI_API_KEY` |
| Gemini | `gemini_explainer.py` | Google | `GOOGLE_API_KEY` |
| Ollama | `ollama_explainer.py` | Local | Ollama server |
| Mock | `mock_explainer.py` | None | Nothing (testing) |

**Usage:**
```python
from src.infrastructure.ai import ExplainerFactory

explainer = ExplainerFactory.create(provider="claude")
explanation = explainer.explain(assessment, snapshot, ticker)
```

### 2. Formula Translator (NEW)

Translates natural language indicator descriptions into formula expressions.

| File | Purpose |
|------|---------|
| `formula_translator.py` | Multi-provider adapter implementation |
| `formula_translator_prompt.py` | Carefully crafted prompt template |

**How it works:**
1. User describes indicator in natural language
2. AI translates to formula syntax
3. Formula is validated by parser
4. Returns formula string or `UNSUPPORTED`

**Usage:**
```python
from src.infrastructure.ai import FormulaTranslatorFactory

translator = FormulaTranslatorFactory.create(provider="claude")
result = translator.translate(
    intent="smoothed RSI with 14-period and 10-day smoothing",
    available_functions={"SMA", "EMA", "RSI", "ATR"},
)
# Returns: "SMA(RSI(14), 10)"
```

**Supported intents:**
- Indicator combinations: "MACD line using 12 and 26 EMAs"
- Smoothing: "exponentially smoothed RSI"
- Normalization: "RSI as percentage of its 20-day average"
- Mathematical operations: "difference between fast and slow EMA"

**Rejected intents (returns UNSUPPORTED):**
- Trading advice: "should I buy?"
- Predictions: "will price increase?"
- Non-formula requests: "explain RSI"
- Unsupported indicators: "Ichimoku cloud"

### 3. Headline Classifier

Classifies news headlines as positive/neutral/negative.

| File | Location | Method |
|------|----------|--------|
| `ai_classifier.py` | `sentiment/` | LLM-based |
| `keyword_classifier.py` | `sentiment/` | Rule-based (default) |

---

## Factory Pattern

All AI components use factories for consistent instantiation:

```python
# Explainers
from src.infrastructure.ai import ExplainerFactory
explainer = ExplainerFactory.create(provider="ollama", model="llama3:8b")

# Formula Translators
from src.infrastructure.ai import FormulaTranslatorFactory
translator = FormulaTranslatorFactory.create(provider="claude")

# Classifiers
from src.infrastructure.sentiment import SentimentFactory
classifier = SentimentFactory.create_classifier(use_ai=True, provider="openai")
```

---

## Environment Variables

| Variable | Used By | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Claude adapters | Required |
| `OPENAI_API_KEY` | OpenAI adapters | Required |
| `GOOGLE_API_KEY` | Gemini adapters | Required |
| `OLLAMA_HOST` | Ollama adapters | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama adapters | `qwen2.5-coder:1.5b` |
| `AI_PROVIDER` | All factories | `claude` |

---

## Error Handling

All adapters raise consistent exceptions:

```python
from src.domain.ports.ai_explainer import (
    ExplainerAuthError,      # Invalid/missing API key
    ExplainerTimeoutError,   # Request timeout
    ExplainerRateLimitError, # Rate limit exceeded
)

from src.application.ports.formula_translator import (
    TranslatorAuthError,
    TranslatorTimeoutError,
    TranslatorRateLimitError,
    FormulaTranslatorError,  # Base class
)
```

---

## Testing

Mock adapters are provided for testing without API calls:

```python
# Use mock explainer
explainer = ExplainerFactory.create(provider="mock")

# Mock translator returns predefined responses
translator = FormulaTranslatorFactory.create(provider="mock")
```

---

## Adding New Providers

1. Create adapter implementing the port protocol
2. Add to factory's provider registry
3. Handle authentication and errors consistently
4. Add tests using mock responses

Example structure:
```python
class NewProviderExplainer:
    """Implements AIExplainer protocol."""

    @property
    def provider_name(self) -> str:
        return "new_provider"

    def explain(self, assessment, snapshot, ticker) -> str:
        # Implementation
        ...
```

---

## Security Notes

- API keys are never logged or exposed in errors
- Prompts are carefully crafted to prevent injection
- AI outputs are validated before use (formulas are parsed)
- No arbitrary code execution from AI responses
