## AI-based sentiment

Examples:

- LLM reads news + social media
- LLM summarizes market mood
- LLM outputs confidence or bias

This is probabilistic and non-deterministic




**If sentiment is unavailable:**

fallback to neutral or ignore sentiment entirely

➡ No rule breaks


## Sentiment Boundary

Sentiment is contextual evidence. Keyword classification is deterministic;
LLM-assisted classification is optional and non-authoritative. Neither path may
bypass SignalEngine, RiskEngine, or MarketContextEngine.
