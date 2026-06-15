# Autonomous Order Execution & Micro-Market Routing (The "Last Mile")
**Date:** June 12, 2026
**Author:** Gemini CLI Agent
**Recommendation Name:** `autonomous_order_execution`

Once `ai-saham` has perfected its analytical brain through Adaptive Regime Tuning (ART) and Portfolio Correlation Orchestration (PCO), the final bottleneck becomes **Human Execution Latency**. 

This document outlines the roadmap to transition the application from a "Decision Support CLI" into a **Deployable Quantitative Trading Bot** capable of managing the "Last Mile" of trading on the Indonesia Stock Exchange (IDX).

---

## 1. The Concept: Solving the "Last Mile" Problem
If the system knows exactly *what* to buy, *when* to buy, and *how much* to buy, requiring a human to manually open a broker application, input a PIN, calculate lot sizes, and place the order introduces fatal latency. This is especially damaging during the highly volatile 09:00–09:05 AM "Golden Window" in the IHSG.

Autonomous Execution replaces human delay and emotion with instantaneous, algorithmic precision.

---

## 2. Pillar I: Direct Broker API Bridging
The Indonesian brokerage ecosystem is highly fragmented, with official FIX protocol access typically reserved for high-net-worth institutional clients.

### Implementation Strategy
- **Adapter Pattern:** Build an `OrderRoutingAdapter` module that abstracts the execution logic.
- **Retail Bridge:** Since open APIs (like those in the US crypto/stock market) are rare in Indonesia, the system will likely require:
    - **Secure Browser Automation:** Encrypted, local-only Playwright instances that act on behalf of the user to inject orders into web-based platforms (e.g., Stockbit Web, IndoPremier).
    - **API Reverse Engineering:** Utilizing internal broker endpoints (with user consent and localized credential storage) to pass `saham size` outputs directly into the market.

---

## 3. Pillar II: Algorithmic Order Types (TWAP/Iceberg)
### The IHSG Illiquidity Problem
Outside of the top 10 Blue Chips (BBCA, BBRI, BMRI, etc.), the IHSG is highly illiquid. If the Portfolio Optimizer suggests buying 5,000 lots of a mid-cap stock, a single "Market Order" will clear the order book and cause massive slippage (pushing the price up against yourself).

### Implementation Strategy
Implement **Smart Order Routing (SOR)** within the execution engine.
- **TWAP (Time-Weighted Average Price):** The bot automatically slices the 5,000-lot order into fifty 100-lot orders, executing them every 5 minutes over the trading day to minimize market impact.
- **Iceberg Orders:** Hiding the true size of the order to prevent predatory front-running by local market makers.

---

## 4. Pillar III: Level 2 "Anti-Spoofing" (Tape Reading)
### The "Jemuran" Trap
The IHSG order book is notorious for *"Jemuran"* (Fake Bids/Offers). Market makers place massive fake bid walls to create the illusion of heavy support, enticing retail to buy, only to pull the bids milliseconds before execution.

### Implementation Strategy
Before the autonomous system executes an order, it performs a micro-second "Tape Read."
- **Logic:** The execution engine monitors the Level 2 Order Book for 3-5 seconds prior to entry.
- **Action:** If a massive bid wall suddenly disappears as the price approaches it, the system flags **"Spoofing Detected"** and immediately aborts the automated entry.
- **Outcome:** Protects the automated capital from classic IDX liquidity traps.

---

## Conclusion: The Fully Autonomous Fund
By implementing Autonomous Order Execution, `ai-saham` completes its evolution. 

It becomes a system that can run headless on a local server, wake up at 08:30 AM, scrape the pre-open movers, adjust its thresholds based on the global macro regime, detect fake liquidity, and execute precision algorithmic orders across the IDX—all with zero human emotion or delay.

---

## Implementation Status (Audit June 2026)

- **Pillar I (Broker Bridging):** **PENDING.** While the `StockbitPlaywrightBrokerProvider` implements automated data fetching (movers, orderbooks) by hijacking the browser's network layer, it does NOT yet implement order placement or an `OrderRoutingAdapter`.
- **Pillar II (Algo Orders):** **NOT MET.** TWAP and Iceberg logic are not present in the current codebase.
- **Pillar III (Anti-Spoofing):** **NOT MET.** There is no Level 2 "Tape Reading" or spoofing detection logic implemented.

**Conclusion:**
This document remains a **Strategic Roadmap.** The system has achieved the "Data Bridge" milestone (automated scraping via Playwright), but the "Execution" half (placing orders) is not yet implemented to maintain the project's "Decision Support" focus and avoid the complexities of autonomous brokerage interaction.
