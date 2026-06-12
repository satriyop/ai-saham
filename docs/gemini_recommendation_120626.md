# High-Impact Recommendations for AI-Saham (IHSG Focus)
**Date:** June 12, 2026
**Author:** Gemini CLI Agent

Following a comprehensive audit of the `ai-saham` codebase and an objective analysis of current Indonesia Stock Exchange (IDX) market dynamics, the following three improvements are identified as having the highest potential impact on trading performance, usability, and risk management.

---

## 1. Logic: Advanced "Smart Money" Broker-Weighted Flow
**Category:** Trading Strategy & Signal Quality

### Observation
The current implementation of `FOREIGN_FLOW` and `FOREIGN_VWAP` treats all foreign or domestic entities as aggregate blocks. While useful, this masks the significant variance in signal quality between different broker types.

### Contextual Edge (IHSG)
IDX is one of the few markets globally that publicly discloses broker-level transaction data daily. In the Indonesian context, tracking "Bandarmology" (the study of market makers/big players) is a proven edge. Institutional brokers (e.g., BK, AK, KZ) typically represent "Smart Money," while retail-heavy brokers (e.g., YP, PD) often represent "Noise."

### Recommendation
Implement a **Weighted Accumulation Score** utilizing the `top_buyers` and `top_sellers` data already present in the `BrokerSummary` entity.
- **Implementation:** Assign weights to brokers based on their institutional vs. retail profile.
- **Logic:** `Signal = Sum(Volume * BrokerWeight)`.
- **Outcome:** A buy signal from a "Smart Money" broker generates higher conviction than a retail-led surge.

### Impact
Significantly improves signal-to-noise ratio, especially in small-to-mid cap stocks where retail fakeouts are common.

---

## 2. Usability: Automated Real-time Data Bridge (Live Scraper)
**Category:** Usability & Execution Efficiency

### Observation
The pre-open screening workflow (`docs/intraday_trader_howto.md`) requires users to manually scrape IEV (Intraday Expected Volume) from Stockbit and paste it into the CLI as a JSON string during the critical 08:45–09:00 AM window.

### Contextual Edge (IHSG)
The 15-minute IDX pre-open window is the most volatile and opportunity-rich period for intraday traders. The current manual process is high-friction, error-prone, and consumes valuable time during the "Golden Window."

### Recommendation
Develop a **Browser Automation Adapter** (using Playwright) to bridge the "Data Gap."
- **New Command:** `saham screen pre-open --auto`.
- **Workflow:** The tool launches a headless browser, navigates to the Stockbit Movers section, scrapes live IEV data, and injects it directly into the screener engine.

### Impact
Transforms the tool from a "static calculator" into a "near real-time scanner," enabling users to respond to pre-open surges instantly.

---

## 3. Strategy/Risk: Market Microstructure Awareness (FCA & Notasi Khusus)
**Category:** Risk Management & Safety

### Observation
The current `RiskEngine` assumes all stocks follow standard technical behaviors. It does not account for regulatory states that fundamentally change how a stock's price is formed.

### Contextual Edge (IHSG)
IDX recently introduced the **Full Call Auction (FCA)** for stocks in the "Special Monitoring List" (*Papan Pemantauan Khusus*). Stocks under FCA or with specific "Notasi Khusus" (e.g., notation X, E) have different tick sizes, different Auto Rejection limits, and do not follow standard price discovery patterns. Standard indicators like RSI or ATR are often "broken" or misleading for these stocks.

### Recommendation
Integrate **Stock Notation Awareness** into the core Domain models and Risk Engine.
- **Data Integration:** Fetch "Notasi Khusus" status from the IDX API.
- **Risk Logic:** Automatically flag stocks with notation "X" or "E" as `HIGH_RISK` regardless of technicals.
- **Backtest Logic:** Adjust tick-size and slippage assumptions for FCA stocks.

### Impact
Protects users from "value traps" and "liquidity traps" caused by regulatory changes, ensuring the tool remains robust against IHSG's evolving microstructure.

---

## Summary of Impact

| Recommendation | Primary Benefit | ROI for User |
| :--- | :--- | :--- |
| **Broker-Weighted Flow** | Accuracy | Better entry signals by following institutional lead. |
| **Live Scraper Bridge** | Speed | Captured opportunities in the 08:45-09:00 AM window. |
| **Microstructure Logic** | Safety | Avoidance of high-risk regulatory traps (FCA/Notasi). |
