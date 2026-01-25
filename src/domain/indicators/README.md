# STRONGLY RECOMMENDED


## Technical indicators

TA-Lib or pandas-ta

- Option A: pandas-ta
Pure Python
Easy to read
Good for explainability
Easier for AI agents to reason about


**Wrap indicators inside: domain/indicators/**
**Never call TA-Lib directly from rules**
Always wrap → keeps tests clean.


## Sentiment indicator

Rules:
- Input = structured data (counts, scores, ratios)
- Output = numeric or categorical score
- No network, no LLM, no scraping

Rules don’t care where sentiment came from.

Example:

```
if sentiment_score > 0.6 and rsi < 30:
    signal = "bullish"
```

**If sentiment is unavailable:**

fallback to neutral or ignore sentiment entirely

➡ No rule breaks

Examples:

- News keyword scoring
- Bullish / bearish counts
- Volume of positive vs negative mentions

Rule-based weighting : This behaves like an indicator

Deterministic : (TBD Approach, Future dev)
- vaderSentiment
- keyword-based scoring

## Risk Profile + Sentiment
**Risk profiles + sentiment (this is important)**

1. Conservative

- Sentiment is advisory only
- Never overrides price/volume signals
- Acts as confidence modifier

2. Balanced

- Sentiment can confirm signals
- May filter false positives

3. Aggressive
- Sentiment can lead
- Price can confirm later

4. Full AI
- Sentiment can dominate
- Rules are bypassed intentionally
- All of this is driven by config, not code.