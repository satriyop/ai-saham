# AI Modes

AI Saham is designed with AI as an **optional enhancement**, not a requirement. The system must be fully functional and valuable without any AI integration.

---

## Current State: AI is OFF

**Version 0.1.0 operates entirely without AI.**

All analysis is:
- **Deterministic** - Same input always produces same output
- **Rule-based** - Uses proven technical indicator calculations
- **Transparent** - Every signal has clear rationale
- **Reproducible** - Results can be audited and verified

---

## Design Principle

> "If AI disappears tomorrow, this system must still be valuable."

This principle ensures:
1. Core functionality never depends on external AI services
2. Users aren't locked into AI provider costs
3. Analysis can be performed offline
4. Results are explainable without "AI said so"

---

## Planned AI Integration (Future)

When AI is added, it will follow strict architectural rules:

### AI as Advisor, Not Decision Maker

```
Rule-Based Analysis --> AI Advisor --> Enhanced Output
                           |
                           v
                    Explanation Layer
```

AI will **augment** rule-based analysis, not replace it:
- Provide natural language explanations
- Suggest additional context
- Identify patterns across multiple stocks
- Generate research summaries

### Opt-In Only

AI features will require explicit activation:

```bash
# Default: No AI
saham risk BBCA

# Future: With AI enhancement
saham risk BBCA --ai
```

### Traceable Contributions

Every AI contribution will be:
- Clearly labeled as AI-generated
- Logged for audit purposes
- Separate from deterministic signals

---

## Future AI Features (Roadmap)

### Phase 1: Explanation Enhancement

- Natural language summaries of technical analysis
- Context about why indicators matter
- Educational insights for beginners

### Phase 2: Pattern Recognition

- Multi-stock correlation analysis
- Sector trend identification
- Anomaly detection in price movements

### Phase 3: Research Assistant

- News sentiment summary
- Earnings report highlights
- Competitor comparison

---

## AI Provider Strategy

The system will support multiple AI providers through adapter pattern:

| Provider | Use Case |
|----------|----------|
| Claude (Anthropic) | Primary analysis assistant |
| Gemini (Google) | Alternative provider |
| Local LLM | Offline AI capability |

Provider selection will be configurable, not hardcoded.

---

## Why Not Full AI?

Some stock analysis tools are "AI-first". Here's why we're different:

| Concern | Our Approach |
|---------|--------------|
| **Cost** | AI APIs cost money; rule-based is free |
| **Reliability** | AI services can go down; rules always work |
| **Auditability** | Rules are transparent; AI is a black box |
| **Speed** | Local computation is instant; AI has latency |
| **Privacy** | Data stays local; AI requires sending data |

---

## For Developers

If you're extending AI Saham with AI features:

1. **Put AI in infrastructure layer** - Never in domain
2. **AI adapter implements domain port** - Domain defines interface
3. **Make AI optional** - Feature works without it
4. **Log AI contributions** - For debugging and audit
5. **Test without AI** - Don't break core functionality

Example port (future):

```python
# In src/domain/ports/ai_advisor.py
class AIAdvisor(Protocol):
    def enhance_analysis(self, snapshot: IndicatorSnapshot) -> str:
        """Return AI-enhanced explanation."""
        ...
```

The domain defines what it needs; infrastructure provides it.
