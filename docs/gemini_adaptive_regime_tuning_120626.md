# Adaptive Regime Tuning (ART): The Automated Learning Loop
**Date:** June 12, 2026
**Author:** Gemini CLI Agent
**Recommendation Name:** `adaptive_regime_tuning`

This document outlines the architectural roadmap for transforming `ai-saham` from a static analysis tool into a **Self-Optimizing Strategy Lab.** The core objective is to implement a learning loop that automatically tunes signal thresholds based on empirical market performance in the Indonesia Stock Exchange (IHSG).

---

## 1. The Concept: Beyond Static Thresholds
Most trading systems fail because they use static parameters (e.g., "Always buy at RSI 30"). In reality, the "correct" RSI threshold for a stock like BBRI changes depending on whether the IHSG is in a **Bull, Bear, or Sideways Regime.**

**Adaptive Regime Tuning (ART)** creates a feedback loop that identifies the current regime and adjusts rule weights and thresholds to match historical "What is working now" data.

---

## 2. The 4-Phase Learning Loop

### Phase I: Observation (Regime-Aware Logging)
When a signal is generated and logged via `saham screen log`, the system must capture more than just the signal. It must capture the **"Market DNA"** at that moment.
- **Action:** Extend the `Journal` schema to include:
    - `ihsg_trend`: (UP/DOWN/SIDE)
    - `sector_rsi`: (Momentum of the stock's sector)
    - `macro_volatility`: (USD/IDR and Commodity price change)
    - `indicator_snapshot`: The raw values of all indicators (RSI, MFI, Flow).

### Phase II: Verification (The Ground Truth)
The existing `saham screen review` command remains the source of truth, but its output is now used as the **Reward Signal** for the learning engine.
- **Action:** Calculate the "Signal Accuracy" (Did the Bullish signal actually result in a positive 5-day return?).

### Phase III: Attribution (The Intelligence)
A new **`CorrelationEngine`** service analyzes the relationship between the "Market DNA" (Phase I) and the "Reward Signal" (Phase II).
- **Discovery Logic:** 
    - *"During 'High Volatility' regimes, Foreign Flow has 80% accuracy."*
    - *"During 'Sector Rotation' regimes, RSI < 30 has only 20% accuracy."*
- **Outcome:** Identifies **Feature Importance** per regime.

### Phase IV: Adaptation (Automated Tuning)
This is the candidate for full automation.
- **Action:** The system generates a `regime_overrides.yaml`.
- **Logic:** When running a screen or risk assessment, the `RuleInterpreter` checks if a regime override exists for the current market state.
- **Automation:** If the "Learning Confidence" is > 85%, the system can automatically update these overrides without user intervention.

---

## 3. IHSG Contextual Advantages

### A. Sector-Specific Tuning
IHSG is dominated by sectoral cycles (Banks vs. Commodities). ART allows the system to learn that **Coal stocks (ADRO, ITMG)** require different RSI thresholds than **Consumer stocks (ICBP, UNVR)** due to their inherent volatility profiles.

### B. Foreign Flow "Motive" Analysis
ART can learn to distinguish between "Accumulation for a Breakout" and "Accumulation to Defend a Floor" by correlating the `VWAP_DISC` with the subsequent price outcome.

---

## 4. Implementation Requirements

| Component | Change Required |
| :--- | :--- |
| **Domain** | New `MarketRegime` value object and `AttributionResult` entity. |
| **Application** | `AttributionService` to perform statistical correlation on `journals/*.csv`. |
| **Infrastructure** | `MacroDataProvider` (Yahoo Finance/IDX) to fetch Index and Currency data. |
| **CLI** | `saham learn` command to trigger the manual/automated optimization. |

---

## 5. Strategic Objective: The "Self-Correction" Loop
The ultimate objective is a system that **Self-Corrects.** 
- If the market switches from a Bull to a Bear regime, the user will inevitably see a few "Failed" signals in their journal. 
- The ART system will detect these failures, attribute them to the regime shift, and **instantly tighten the entry requirements** for all future signals. 

This creates an application that doesn't just "show signals" but **"understands its own limitations"** and evolves to overcome them.

---

## Implementation Status (Audit June 2026)

- **Phase I (Observation):** **PARTIALLY MET.** The `AccumulationJournalEntry` domain object has been enriched with the `regime` field, along with `preset`, `classification`, and `failed_gates`. However, specific fields like `sector_rsi` and `macro_volatility` are not yet persisted in the journal.
- **Phase II (Verification):** **MET.** The `accumulation_review` command (via `saham swing review`) calculates actual returns (5d, 10d, 20d) and identifies winners, providing the necessary "Reward Signal."
- **Phase III & IV (Attribution & Adaptation):** **PENDING.** The `CorrelationEngine` and automated `regime_overrides.yaml` generation are not yet implemented. The `saham learn` command is missing.
- **Domain/Application:** **MET.** `MarketRegimeUseCase` and `MarketRegimeResponse` are fully implemented in `src/application/use_case/market_regime.py` and are integrated into the swing and intraday workflows.

**Conclusion:**
The foundation for Adaptive Regime Tuning is solid. The system now "knows" the market regime during analysis and logs it, but the automated feedback loop to tune thresholds (the "Learning" part) remains a manual analytical task for the user using the `review` data.
