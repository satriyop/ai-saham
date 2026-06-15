# Sentiment Impact Learning: From Classification to Catalyst Intelligence
**Date:** June 12, 2026
**Author:** Gemini CLI Agent
**Recommendation Name:** `sentiment_impact_learning`

This document outlines the roadmap to evolve the current sentiment analysis feature from a basic "Positive/Negative" classifier into a **Catalyst-Aware Intelligence System** that learns to predict market responses in the Indonesia Stock Exchange (IHSG).

---

## 1. Feature: Catalyst Taxonomy & Contextual Labeling
**Objective:** Moving Beyond Simple Sentiment to Actionable Catalysts.

### The Problem
The current `AIClassifier` only outputs `POSITIVE/NEGATIVE/NEUTRAL`. This treats an "Earnings Beat" the same as a "Stock Split" announcement, despite these having fundamentally different price trajectories and institutional motivations.

### The Solution
Upgrade the AI prompt and domain model to support **Catalyst Taxonomy**.
- **Logic:** Classify headlines into categories specific to the IDX market:
    - `EARNINGS`: (Quarterly reports, profit projections)
    - `CORP_ACTION`: (Stock splits, rights issues, buybacks)
    - `REGULATORY`: (Government policy, export bans, OJK/IDX mandates)
    - `MACRO`: (Interest rates, commodity price surges like Coal/Nickel)
    - `GOVERNANCE`: (CEO changes, scandals, audits)
- **Trader Value:** Enables the user to prioritize "High-Impact" catalysts (like Regulatory shifts) over "Medium-Impact" noise.

---

## 2. Feature: Conglomerate-Group Propagation
**Objective:** Capture Systemic Sentiment across Indonesian "Groups."

### The Problem
News about a specific ticker is often driven by broader sentiment surrounding its parent conglomerate or "Group" (e.g., Salim, Barito, Astra, BUMN). Currently, news about `BREN` is analyzed in isolation, ignoring major news about the `Barito Group` that might impact it.

### The Solution
Implement a **Group Awareness Layer** in the `FetchSentimentUseCase`.
- **Logic:** Map tickers to their respective "Groups" (e.g., `TLKM -> BUMN`, `ADRO -> Adaro Group`). 
- **Workflow:** When fetching sentiment for `TLKM`, the system also pulls and weighs headlines for `BUMN` and `IDX-INFRASTRUCTURE`.
- **Impact:** Identifies "Group-Contagion" sentiment where a scandal or win for one affiliate predicts a move for another before specific ticker headlines appear.

---

## 3. The Loop: Sentiment Impact Auditing (The Learning Loop)
**Objective:** Automate the Correlation between News and Price.

### The Problem
AI classification is probabilistic and can be "wrong" about market reaction. In the IDX, "Good News" often leads to a "Sell on News" event. Without a learning loop, the system continues to flag these as `LOW_RISK`.

### The Solution
Create a **`SentimentAudit` Service** to bridge Perception and Reality.
- **Phase I (Record):** Persist the `SentimentSnapshot` and `CatalystType` into the local SQLite database at the time of analysis.
- **Phase II (Review):** After 1, 3, and 5 trading days, the system automatically fetches the `actual_price_delta`.
- **Phase III (Learn):** A correlation engine analyzes the success rate of specific catalysts per sector.
    - *Example Discovery:* "For the Banking sector, 'Positive Earnings' news has a 70% correlation with price gains over 5 days."
    - *Example Discovery:* "For Penny stocks, 'Positive Corporate Action' has a -40% correlation (Sell on News)."
- **Outcome:** The `RiskEngine` automatically adjusts its weights based on this "Actual Impact" data.

---

## Summary of Implementation

| Feature | Technical Target | IHSG-Specific Edge |
| :--- | :--- | :--- |
| **Catalyst Taxonomy** | `src/infrastructure/ai/ai_classifier.py` | Distinguishes between "Noise" and "Real Momentum." |
| **Group Propagation** | `src/application/services/group_mapping.py` | Captures conglomerate-driven volatility. |
| **Impact Auditing** | `src/infrastructure/persistence/sentiment_repository.py` | **(The Learning Loop)**: Predicts actual price moves based on historical catalyst performance. |

---

## Implementation Status (Audit June 2026)

- **Catalyst Taxonomy:** **MET.** The `CatalystType` enum (EARNINGS, CORP_ACTION, etc.) is fully integrated into the domain model and AI classification prompts.
- **Group Propagation:** **MET.** `GroupMappingService` is implemented and used to contextually link tickers to their respective conglomerates (Astra, BUMN, etc.) during sentiment analysis.
- **Impact Auditing:** **MET.** `AuditSentimentUseCase` and the `saham sentiment audit` command are fully functional, providing accuracy reports for sentiment vs. price performance over 1, 3, and 5-day horizons.

**Conclusion:**
This recommendation has been **fully implemented.** The sentiment engine is now one of the most advanced parts of the system, capable of not only classifying news but also auditing its own historical "Catalyst Intelligence" against actual IHSG market moves.
