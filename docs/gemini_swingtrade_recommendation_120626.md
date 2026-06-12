# High-Impact Swing Trading Recommendations for AI-Saham (IHSG)
**Date:** June 12, 2026
**Author:** Gemini CLI Agent

Following an audit of the `ai-saham` swing trading components (`swing_commands.py`, `AccumulationScreenUseCase`) and research into IHSG institutional cycles, these three recommendations focus on improving win-rates and trade management for positions held over 5–20 days.

---

## 1. Feature: Multi-Timeframe Trend Alignment (Weekly Filter)
**Category:** Strategic Precision & Signal Quality

### Observation
The current technical assessments (`AssessRiskUseCase`) rely exclusively on daily price action. Daily signals frequently produce "fakeouts" when the broader weekly trend is bearish.

### Contextual Edge (IHSG)
In the Indonesian market, institutional "sector rotation" is clearly visible on weekly charts. A daily "Buy" signal in a stock that is trending down on the weekly EMA-10 is statistically more likely to fail as a swing trade.

### Recommendation
Implement **Weekly Interval Support** in the `IndicatorRegistry`.
- **Logic:** Add a `MAJOR_TREND` indicator that resamples daily data into weekly bars and calculates a 10-period Weekly EMA.
- **UI:** In the `saham swing` command, include a "Weekly Alignment" status:
    - **[Trend-Aligned]**: Daily Buy + Weekly Up (High Conviction).
    - **[Counter-Trend]**: Daily Buy + Weekly Down (High Risk/Short-term Bounce).

---

## 2. Feature: Institutional "Silent Accumulation" Scanner
**Category:** Alpha Generation (Bandarmology)

### Observation
Existing screeners focus on active accumulation (High IEV, High Score). This often identifies stocks that have *already* started moving or are widely discussed.

### Contextual Edge (IHSG)
"Silent Accumulation" occurs when institutions build large positions over 20–40 days while keeping price volatility low to avoid drawing attention. In IHSG, this is a precursor to massive breakouts. 

### Recommendation
Implement a specialized **"Silent Accumulation" mode** for the accumulation screener.
- **Logic:** Filter for tickers meeting three "Low-Profile" criteria:
    1. **Positive Net Foreign Flow** over the last 30 days.
    2. **Rising OBV (On-Balance Volume)**: Volume is consistently higher on up-days than down-days.
    3. **Tight Price Consolidation**: Bollinger Band Width is at a 30-day low (compression).
- **Outcome:** Surfaces "coiled spring" setups before they appear on standard momentum screeners.

---

## 3. Workflow: Systematic Exit Monitor (`saham swing manage`)
**Category:** Workflow Efficiency (Lifecycle Management)

### Observation
The application is currently optimized for "Discovery" (finding entries) but lacks systematic "Management" (monitoring exits). Swing traders often hold too long or miss signs of institutional distribution.

### Contextual Edge (IHSG)
Institutional support in IHSG is not permanent. When "Smart Money" shifts from accumulation to distribution (selling), it often takes several days to complete. Detecting the *start* of this shift is the key to preserving swing profits.

### Recommendation
Introduce a **`saham swing manage`** command.
- **Logic:** Link this to a user's watchlist (`.watchlist.json`). The command monitors open positions for "Thesis Failure" triggers:
    1. **Distribution**: Foreign Net Flow turns negative for 3+ consecutive days.
    2. **Floor Break**: Price closes below the **Foreign VWAP** (the "institutional cost basis" floor).
    3. **Momentum Loss**: Price closes below the Daily EMA-10.
- **UI:** A simple status board:
    - **BBRI**: Thesis Intact (Hold)
    - **TLKM**: **[EXIT WARNING]** - Institutional Distribution Detected.

---

## Summary of Implementation

| Feature | Technical Target | Swing Trade Edge |
| :--- | :--- | :--- |
| **Weekly Filter** | `IndicatorRegistry` / `CandleResampler` | Filters noise; ensures trading with the "Big Money" trend. |
| **Silent Scanner** | `AccumulationScreenUseCase` | Identifies low-risk entries before the "masses" arrive. |
| **Exit Monitor** | `swing_commands.py` (new command) | Replaces emotional selling with data-driven trade management. |
