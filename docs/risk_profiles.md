# Risk Profiles Guide

AI Saham uses three risk profiles for deterministic, rule-based risk assessment. Each profile applies different thresholds and decision logic to technical indicators.

---

## Profile Overview

| Profile | Philosophy | Decision Logic |
|---------|------------|----------------|
| **conservative** | Safety first | Requires multiple indicators to agree |
| **balanced** | Moderate approach | Majority of indicators rules |
| **aggressive** | Opportunity seeking | Single indicator can signal |

---

## Conservative Profile

**Best for:** Long-term investors, retirement accounts, risk-averse traders

**Characteristics:**
- Strict RSI thresholds (overbought > 75, oversold < 25)
- Requires both momentum and trend indicators to agree
- Higher confidence requirements for signals
- Minimizes false positives at cost of missing some opportunities

**When to use:**
- Capital preservation is priority
- You prefer fewer, higher-conviction signals
- You're investing money you can't afford to lose
- You want to avoid emotional trading

**Thresholds:**
| Indicator | Overbought | Oversold |
|-----------|------------|----------|
| RSI | > 75 | < 25 |

---

## Balanced Profile

**Best for:** General analysis, moderate risk tolerance, learning

**Characteristics:**
- Standard RSI thresholds (overbought > 70, oversold < 30)
- Majority rule for conflicting indicators
- Balanced between sensitivity and reliability
- Good baseline for comparison

**When to use:**
- Default choice for most analysis
- You want balanced risk/reward
- You're comparing multiple stocks
- You're new to technical analysis

**Thresholds:**
| Indicator | Overbought | Oversold |
|-----------|------------|----------|
| RSI | > 70 | < 30 |

---

## Aggressive Profile

**Best for:** Active traders, short-term positions, higher risk tolerance

**Characteristics:**
- Looser RSI thresholds (overbought > 65, oversold < 35)
- Single indicator can trigger a signal
- More sensitive to market movements
- More signals, but more noise

**When to use:**
- You're comfortable with higher risk
- You want early entry points
- Short-term trading strategies
- You can tolerate more false signals

**Thresholds:**
| Indicator | Overbought | Oversold |
|-----------|------------|----------|
| RSI | > 65 | < 35 |

---

## Risk Levels Explained

Each assessment returns one of three risk levels:

### HIGH_RISK

Indicators suggest elevated risk conditions:
- RSI in overbought territory (potential for pullback)
- Price significantly above moving averages
- Multiple warning signals present

**Action consideration:** Review position sizing, consider taking profits

### MODERATE

Indicators suggest neutral conditions:
- RSI in normal range
- Price near moving averages
- No strong directional signals

**Action consideration:** Monitor for changes, no urgent action needed

### LOW_RISK

Indicators suggest favorable conditions:
- RSI in oversold territory (potential bounce)
- Price at or below moving averages
- Multiple bullish signals present

**Action consideration:** Potential entry point for long positions

---

## Comparing Profiles

Use `--all` flag to see how a stock looks across all profiles:

```bash
saham risk BBCA --all
```

This helps you understand:
- How sensitive each profile is
- Whether signals are strong (all profiles agree) or weak (profiles disagree)
- Which profile best matches your risk tolerance

---

## Confidence Score

Each assessment includes a confidence score (0-100):

| Score | Interpretation |
|-------|----------------|
| 80-100 | Strong signal, multiple indicators agree |
| 60-79 | Moderate signal, some agreement |
| 40-59 | Weak signal, indicators mixed |
| 0-39 | Very weak, likely noise |

Higher confidence means more indicators point in the same direction.

---

## Important Notes

1. **No profile is "better"** - Choose based on your personal risk tolerance
2. **Profiles are deterministic** - Same data always produces same result
3. **These are signals, not predictions** - Use as one input in your analysis
4. **Always do your own research** - This tool provides analysis, not financial advice

---

## Customizing Profiles

Profile configurations are stored in `config/`:
- `conservative.yaml`
- `balanced.yaml`
- `aggressive.yaml`

Advanced users can modify thresholds, but understand the implications before changing defaults.
