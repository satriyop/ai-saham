# Gemini Swing Trading Improvements — IHSG Context
**Date:** 2026-06-15
**Context:** Indonesia Stock Exchange (IDX / IHSG)

Based on an analysis of institutional behavior and "Bandarmology" patterns in the Indonesia Stock Exchange, these five refinements are recommended for the swing trading workflow (`saham trade swing`).

---

## 1. Sector Breadth Confirmation (The "Rotation" Signal)

### The Behavior
In the IHSG, foreign institutions rarely accumulate a single stock in isolation. They typically rotate into entire sectors (e.g., Big Banks, Coal, or Telco). A swing setup in BBRI is significantly more likely to succeed if BBCA and BMRI are also seeing positive foreign flow.

### Recommendation
Add a **Sector Context** layer to the `AccumulationScreenUseCase`.

*   **Metric:** `% of Tickers in Sector with Foreign-Net-Buy > 0` over the same window.
*   **Logic:** If Sector Breadth ≥ 60%, apply a +10 point "Rotation Bonus" to the individual stock's score.
*   **Rationale:** Validates that the move is part of a broad institutional sector rotation rather than an isolated (and potentially transient) trade.

---

## 2. Foreign Broker Clustering (Cluster vs. Whale)

### The Behavior
The current `institutional_broker_present` gate gives a bonus if *one* major broker is present. However, a "Cluster" move (e.g., AK, BK, KZ, and ZP all buying together) is much more robust than a "Whale" move (only AK buying while everyone else sells).

### Recommendation
Replace the binary broker bonus with a **Broker Concentration Index (BCI)**.

*   **Metric:** Count of distinct "Tier 1" foreign brokers in the Top 5 Buyers list.
*   **Logic:**
    *   3+ Tier 1 Brokers: `CLUSTER` (+15 pts)
    *   1-2 Tier 1 Brokers: `STABLE` (+5 pts)
    *   0 Tier 1 Brokers: `RETAIL-LED` (0 pts)
*   **Rationale:** Multi-broker accumulation indicates a consensus among different institutional funds, reducing the risk of a single "Whale" exit crashing the price.

---

## 3. Resistance-Proximity Filtering

### The Behavior
Many high-score accumulation setups fail because they run directly into a "Hard Resistance" just 1-2% above the entry (e.g., the MA200, a Yearly High, or a psychological "Round Number" like Rp 5,000 or Rp 10,000 where IDX tick sizes change).

### Recommendation
Add a **Headroom Gate** to the `foreign-bounce` preset.

*   **Metric:** `Distance to nearest Resistance (MA200 / 52-week High / Psych Level)`.
*   **Logic:** If `Distance < 5%` (the default `foreign-bounce` target), downgrade the `ENTER` decision to `WATCH`.
*   **Rationale:** Ensures that the "Path of Least Resistance" actually supports the 5% profit target before the stock hits a major supply zone.

---

## 4. Regime-Adaptive TP/SL (Dynamic Sizing)

### The Behavior
The current `foreign-bounce` preset uses a fixed 5%/5% (1:1 R:R) model. In a `BULLISH` regime, IHSG stocks often trend for 10%–15% before a meaningful pullback. In a `SIDEWAYS` or `WEAK` regime, 5% is often the maximum "swing" available.

### Recommendation
Scale the Profit Target based on the `MarketRegimeResponse`.

*   **Logic:**
    *   `BULLISH`: Target 8% | Stop 4% (2:1 R:R)
    *   `SIDEWAYS`: Target 5% | Stop 5% (1:1 R:R)
    *   `WEAK`: Target 3% | Stop 3% (Tight Scalp)
*   **Rationale:** Maximizes gains during trending markets while protecting capital with smaller, high-probability targets during uncertain market conditions.

---

## 5. Dividend-Cycle Awareness (The "Ex-Date" Trap)

### The Behavior
Indonesian blue-chips (the primary targets of foreign accumulation) often see massive artificial inflow before the "Cum Date" for dividends, followed by an "Ex-Date" price drop that often exceeds the dividend yield. Foreign accumulation signals during this cycle are often skewed by dividend-stripping strategies rather than structural positioning.

### Recommendation
Introduce a **Corporate Action Filter**.

*   **Logic:** Automatically flag as `AVOID` or add a prominent `!! DIVIDEND RISK` warning if the ticker is within 5 trading days of an `Ex-Date`.
*   **Rationale:** Prevents entering a "High Score" accumulation setup that is about to experience a deterministic gap-down due to dividend adjustments.

---

## Implementation Status (Audit 16 June 2026)

- **Sector Breadth Confirmation:** **NOT MET.** The `AccumulationScreenUseCase` currently processes tickers in isolation. Sector-level aggregation and "Rotation Bonuses" are not yet implemented.
- **Foreign Broker Clustering (BCI):** **MET.** The system implements a **Broker Concentration Index (BCI)** in `AccumulationScreenUseCase.py`. It counts Tier 1 foreign brokers (AK, BK, ZP, etc.) in the Top 5 Buyers and assigns labels: `CLUSTER` (+15 pts), `STABLE` (+5 pts), or `RETAIL-LED` (0 pts). This matches the recommendation exactly.
- **Resistance-Proximity Filtering:** **NOT MET.** The `foreign-bounce` preset and Risk Engine do not currently calculate distance to major resistance levels (MA200, 52-week High) as a decision gate.
- **Regime-Adaptive TP/SL:** **NOT MET.** The `foreign-bounce` preset in `swing_commands.py` uses fixed `Decimal("5")` constants for take-profit and stop-loss, regardless of the current market regime.
- **Dividend-Cycle Awareness:** **NOT MET.** Corporate action data and dividend ex-date filtering are not yet integrated into the analysis pipeline.

**Conclusion:**
The recommendation to refine Bandarmology signals through **Broker Clustering (BCI)** has been **successfully implemented and verified** in both the screener logic and the CLI display. This provides a significant edge in identifying high-conviction institutional moves. The remaining recommendations—particularly Resistance Filtering and Adaptive Targets—remain high-value targets for the next development phase to further improve the win rate and profit factor of the swing trading workflow.
