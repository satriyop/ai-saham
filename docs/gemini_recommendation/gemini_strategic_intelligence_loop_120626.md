# Strategic Intelligence & Learning Loops for IHSG
**Date:** June 12, 2026
**Author:** Gemini CLI Agent
**Recommendation Name:** `strategic_intelligence_loop`

Following a deep audit of the `ai-saham` architecture and its real-world performance in the Indonesia Stock Exchange (IDX), this document outlines the strategy for moving from a **static calculator** to an **intelligent, self-optimizing analysis system.**

The goal is to improve signal accuracy and create a permanent learning loop across all features.

---

## 1. Subject: Market Regime Contextualization (The Gatekeeper)
**Objective:** Improve Accuracy by Filtering Out Counter-Trend Signals.

### The Problem
Currently, a "Buy" signal on a ticker like BBRI is evaluated in isolation. However, in the IHSG, individual stocks rarely fight the broader "Market Regime" or "Sector Rotation." Entering a technically perfect setup while the sector is in a death-spiral leads to high failure rates.

### The Solution
Implement a **Global Market Regime Port** that acts as a signal multiplier.
- **Logic:** Before a `LOW_RISK` signal is issued, the system must validate the **Regime Alignment**.
- **IHSG Context:** 
    - **Primary Filter:** IHSG Composite Index trend (Daily EMA 20/50).
    - **Secondary Filter:** Sectoral Index trend (e.g., IDX-FINANCE for banks, IDX-PROPERTIES).
- **Impact:** If the Sector Trend is DOWN, the system automatically downgrades the conviction of any individual ticker signal within that sector.

---

## 2. Subject: Broker Archetype Clustering (The Quality of Money)
**Objective:** Deepen Signal Fidelity via Advanced Bandarmology.

### The Problem
The existing `FOREIGN_FLOW` is a binary "Foreign vs. Domestic" view. In reality, some foreign brokers are institutional "Smart Money" (long-term trend makers), while some domestic brokers are "Fast Money" (speculative noise).

### The Solution
Develop a **Broker Archetype Engine** to weight transaction quality.
- **Logic:** Instead of just summing volume, cluster brokers into archetypes:
    - **Institutional (e.g., BK, AK, KZ):** High-weight signals for sustained swings.
    - **Speculative/Retail (e.g., YP, PD):** Low-weight or "Contrarian" signals.
- **The Learning Loop:** The system should track the "Predictive Power" of specific brokers over a rolling 6-month window. If accumulation by broker "X" consistently leads to a 5% move, the weight of broker "X" increases dynamically.

---

## 3. Subject: Signal-to-Outcome Feedback (The Evolutionary Engine)
**Objective:** Create a Systematic Learning Loop to Auto-Tune Strategy.

### The Problem
The `PaperTradeJournal` and `BacktestEngine` provide results, but they don't provide **Insights**. The system does not "learn" from its failures; it requires the user to manually deduce why a signal failed.

### The Solution
Implement a **Systematic Error Attribution** module.
- **The Loop Logic:**
    1. **Record:** When a signal is logged via `saham screen log`, save a snapshot of *every* indicator (RSI, MFI, VWAP_DISC, Sector_Trend).
    2. **Audit:** After the trade horizon (e.g., 5 days), compare the prediction to the actual price.
    3. **Correlate:** For all failed signals, run a correlation analysis: *"What indicator was consistently 'lying' during these failures?"*
- **Auto-Tuning:** The system generates a **Strategy Modification Proposal** (e.g., *"Historical data shows RSI < 30 has a 30% failure rate when Sector Trend is DOWN. Suggest adding a Sector Filter to your YAML."*)

---

## Implementation Roadmap

| Milestone | Phase | Technical Goal |
| :--- | :--- | :--- |
| **IHSG Context** | Infrastructure | Add `SectorProvider` to fetch IDX sectoral indices. |
| **Archetype Logic** | Domain | Implement weighted scoring in `AccumulationScreenUseCase`. |
| **The Loop** | Application | Develop the `CorrelationEngine` to audit `journals/pre-open.csv`. |

---

## Conclusion
By implementing the **Strategic Intelligence Loop**, `ai-saham` ceases to be a tool that the user "operates" and starts becoming a partner that the user "trains." It shifts the focus from finding *any* signal to finding the *highest-conviction* signal aligned with the current market regime of the Indonesia Stock Exchange.

---

## Implementation Status (Audit June 2026)

- **Market Regime Contextualization:** **MET.** Implemented as `MarketRegimeUseCase`, calculating IHSG benchmark trends and universe-wide breadth (Price vs SMA20 and Foreign Flow breadth).
- **Broker Archetype Clustering:** **NOT MET.** The transaction quality weighting based on "Smart Money" vs "Retail" brokers is not yet implemented.
- **Signal-to-Outcome Feedback:** **PARTIALLY MET.** The `accumulation_review` command (via `saham swing review`) implements the "Audit" and "Correlate" steps by matching journaled signals to actual 5/10/20d returns. However, the automated "Strategy Modification Proposal" generation (the "Auto-Tuning" part) is still a manual analytical process.

**Conclusion:**
The project has successfully bridged the gap between "Signal" and "Outcome" through the journal/review system. The system now provides all the data needed for a Strategic Intelligence Loop, but the final step—automated proposal of strategy changes—is the next frontier for implementation.
