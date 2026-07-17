# ADR-015: Sentiment Analysis Classification

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — deterministic and AI-assisted sentiment remain explicitly separated infrastructure concerns.
**Decision**
Sentiment analysis is classified into two categories:

* Deterministic sentiment (rule-based, keyword matching)
* AI-based sentiment (probabilistic, LLM-assisted)

**Implications**

* Deterministic sentiment lives in `infrastructure/sentiment/keyword_classifier.py`.
* Empty domain placeholder files are not kept; deterministic sentiment was designed for but never placed in the domain layer.
* AI-based sentiment lives in `infrastructure/sentiment/ai_classifier.py` + `infrastructure/ai/sentiment_analyzer.py`.
* Composite provider (`infrastructure/sentiment/composite_provider.py`) merges multiple news sources.
* News sources (`google_news_provider.py`, `cnbc_indonesia_provider.py`, `kontan_provider.py`) are swappable implementations.
* Domain rules must not depend on raw text or LLM outputs.
* Sentiment is contextual input, not a source of truth.

**Rationale**
Prevents misuse of sentiment while enabling future expansion.
