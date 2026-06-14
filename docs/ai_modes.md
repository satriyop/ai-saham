# AI Modes

AI Saham uses AI as an **optional enhancement**, not a requirement. Every feature works fully without AI.

---

## Current State: AI is Optional

AI is integrated as a **read-only research assistant** in specific commands. It never influences deterministic signals, entries, stops, or trading decisions.

### Where AI is Available

| Command | Flag | What AI Adds |
|---------|------|-------------|
| `saham intraday pre-open` | `--with-ai` | Per-ticker research summary via Claude |
| `saham risk <ticker>` | `--with-sentiment` | News sentiment context |
| `saham screen accumulation` | `--with-ai` | Accumulation pattern analysis |
| `saham swing analyze` | `--with-ai` (implied by `--news-provider`) | News sentiment + setup analysis |

Global override:
```bash
saham <command> --no-ai    # Disable AI even if a subcommand enables it by default
saham <command> --news-provider none   # Same effect
```

### Default AI Provider

The default provider is **DeepSeek** (configured in `src/application/services/factory.py` `DEFAULT_PROVIDER`). Switch at runtime:

```bash
saham <command> --provider claude    # Use Anthropic Claude
saham <command> --provider deepseek  # Use DeepSeek (default)
saham <command> --provider none      # No AI (same as --no-ai)
```

### How AI Integrates

```
Deterministic Pipeline ──> ScreenerCandidate ──> Display
                              │
                              ▼ (if --with-ai)
                         AIExplainer (port)
                              │
                              ▼
                         ClaudeAPI / DeepSeekAdapter (infrastructure)
                              │
                              ▼
                         AI summary appended to output (read-only)
```

Key rules:
- **AI never modifies** Scores, decisions, entries, or stops
- **AI only appends** Explanatory text to the output display
- **AI is opt-in** — `--with-ai` or `--news-provider` must be explicitly passed
- **No network = still works** — `--no-ai` mode runs fully offline

---

## Design Principle

> "If AI disappears tomorrow, this system must still be valuable."

This principle ensures:
1. Core functionality never depends on external AI services
2. Users aren't locked into AI provider costs
3. Analysis can be performed offline
4. Results are explainable without "AI said so"

---

## AI Provider Strategy

The system supports multiple AI providers through an adapter pattern:

| Provider | Status | Use Case |
|----------|--------|----------|
| DeepSeek | **Default** | Primary analysis, free-tier capable |
| Claude (Anthropic) | Supported | Alternative, stronger reasoning |
| Gemini (Google) | Planned | Future alternative |
| Local LLM | Planned | Offline AI capability |

Provider selection is configurable, not hardcoded. The `AIExplainer` domain port defines what the system needs; infrastructure provides it.

---

## For Developers

Extending AI capabilities:

1. **AI goes in infrastructure** — Never in domain
2. **AI adapter implements domain port** — `AIExplainer` protocol in domain layer
3. **AI is always optional** — Feature works without it
4. **Log AI contributions** — For debugging and audit
5. **Test without AI** — Don't break core functionality

### Adding a New AI Provider

```python
# In src/infrastructure/ai/
class MyProviderExplainer(AIExplainer):
    def __init__(self, api_key: str, model: str = "default"):
        ...

    def research(self, ticker: str) -> AIContribution:
        ...
```

Register in `factory.py` under the provider switch. The `--provider` flag selects at runtime.

### Adding AI to a New Command

1. Add `--with-ai` / `--no-ai` CLI flag via `_build_ai_researcher()` helper
2. Pass `AIExplainer` into the use case (optional parameter)
3. In the use case, call `ai_explainer.research(ticker)` if provided
4. Append result to output — never use it in decision logic

---

## Why Not AI-First?

| Concern | Our Approach |
|---------|--------------|
| **Cost** | AI APIs cost money; rule-based is free |
| **Reliability** | AI services can go down; rules always work |
| **Auditability** | Rules are transparent; AI is a black box |
| **Speed** | Local computation is instant; AI has latency |
| **Privacy** | Data stays local; AI requires sending data |

AI augments. It does not decide.
