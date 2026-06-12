# High-Impact Technical Indicator Recommendations for AI-Saham (IHSG)
**Date:** June 12, 2026
**Author:** Gemini CLI Agent

Following a technical audit of the `ai-saham` indicator ecosystem and an assessment of established "high-conviction" signals in the Indonesia Stock Exchange (IDX), these three indicators are recommended to bridge current gaps in volume-analysis and trend-robustness.

---

## 1. Money Flow Index (MFI) - "The Volume-Weighted Truth"
**Category:** Volume & Momentum Confirmation

### Observation
Current momentum indicators in the application (`RSI`, `STOCHASTIC`) are "Price-Only" oscillators. They treat a 2% price move on low volume the same as a 2% move on high institutional volume.

### Contextual Edge (IHSG)
In the IHSG, "Price-Volume Divergence" is the most reliable precursor to a trend reversal. Institutional accumulation (Bandarmology) often leaves its footprints in volume before the price makes a significant breakout. MFI is essentially "Volume-Weighted RSI."

### Implementation Strategy
- **Plugin Name:** `MFI`
- **Logic:** Calculate typical price, money flow, and money flow ratio over a 14-period window.
- **Trader Value:** Confirms if a breakout is "Real" (Price Up + MFI Up) or a "Fakeout" (Price Up + MFI Down/Flat).

---

## 2. Ichimoku Kinko Hyo (Kumo Cloud) - "The Swing Standard"
**Category:** Multi-Dimensional Trend & Support/Resistance

### Observation
Existing trend analysis relies on `SMA` and `EMA`, which are one-dimensional and lagging. They provide a "line" of support, whereas the IDX's volatility often requires a "zone."

### Contextual Edge (IHSG)
Ichimoku is a staple of the Indonesian professional trading community. The **Kumo Cloud (Senkou Span)** acts as a volumetric support/resistance zone. Indonesian swing traders typically utilize "Kumo Breakouts" to identify high-probability entries into institutional trends.

### Implementation Strategy
- **Plugin Name:** `ICHIMOKU` (or `KUMO_CLOUD`)
- **Logic:** Implement Tenkan-sen, Kijun-sen, and the two Senkou Spans.
- **Trader Value:** Provides a "one-look" assessment of trend health. If price is above the Cloud, the path of least resistance is up.

---

## 3. Standard VWAP (Market-Wide Execution Benchmark)
**Category:** Execution & Tactical Entry

### Observation
The application currently features `FOREIGN_VWAP`, which is excellent for tracking foreign investor cost-basis. However, it lacks a standard **VWAP** that accounts for total market participation (Foreign + Domestic).

### Contextual Edge (IHSG)
VWAP is the universal benchmark for "Fair Value" in daily trading. In the IHSG, buying a stock significantly above the daily VWAP is considered "chasing," as you are paying more than the average participant for that day. 

### Implementation Strategy
- **Plugin Name:** `VWAP`
- **Logic:** `Sum(TypicalPrice * Volume) / Sum(Volume)` reset daily for intraday, or rolling for swing.
- **Trader Value:** 
    - **Intraday:** Primary filter—only go long if price > VWAP.
    - **Swing (Rolling):** Identifies the market-wide cost basis, acting as a "Magnet" for price pullbacks.

---

## Summary of Impact

| Indicator | Complexity | Domain Addition | IHSG Edge |
| :--- | :--- | :--- | :--- |
| **MFI** | Low | Volume Momentum | Filters out "Hollow" price moves/fakeouts. |
| **Ichimoku** | Medium | Zone-based Support | High-conviction trend filter for swing trades. |
| **Standard VWAP**| Low | Execution Logic | Benchmarks "Fair Entry" relative to all participants. |

---

### Integration Note
These three indicators complement the existing `FOREIGN_FLOW` and `FOREIGN_VWAP` by providing a broader market context. While the existing indicators tell you what **Foreigners** are doing, these additions tell you what the **Market** as a whole is confirming.
