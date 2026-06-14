# High-Impact Intraday Recommendations for AI-Saham (IHSG)
**Date:** June 12, 2026
**Author:** Gemini CLI Agent

Following a deep audit of the `ai-saham` intraday logic (`PreOpenScreenUseCase`) and a review of IDX market microstructure, these three recommendations target the "08:45–09:05 AM Golden Window" to improve decision speed and capital protection.

---

## 1. Feature: ARA/ARB Guardrails & "Distance to Limit"
**Category:** Risk Management & Strategy Precision

### Observation
The current screener calculates entry ranges based on ATR, but it does not account for the hard price ceilings (ARA) and floors (ARB) enforced by the IDX.

### Contextual Edge (IHSG)
IDX uses symmetrical Auto-Rejection limits (20%, 25%, or 35% depending on the price band). Intraday traders in Indonesia often look for "Momentum ARA" (stocks likely to hit the upper limit) or must avoid "ARB Traps" (stocks locked at the floor with no buyers). 

### Recommendation
Integrate **Auto-Rejection Calculation** into the `ScreenerCandidate` domain model.
- **Logic:** Compute `ara_price` and `arb_price` using the standard IDX price bands:
    - Rp 50 - Rp 200: 35%
    - > Rp 200 - Rp 5,000: 25%
    - > Rp 5,000: 20%
- **UI:** Display "Distance to ARA %" in the CLI output.
- **Signal:** Add a warning if `ATR-Stop` is below the `arb_price`, as the stop-loss might become "un-executable" if the stock locks at ARB.

---

## 2. Workflow: IEV Velocity Tracking (Pre-Open Momentum)
**Category:** Data Fidelity & Institutional Signal

### Observation
The `pre-open` command takes a static snapshot of IEV (Intraday Expected Volume). This provides a "point-in-time" view but misses the *behavioral intent* of big players.

### Contextual Edge (IHSG)
Institutional players in Indonesia often wait until the final minutes of the pre-open (08:58–08:59) to place large orders to avoid revealing their hand. A stock with a steady IEV is less interesting than a stock whose IEV doubles in the last 120 seconds.

### Recommendation
Implement **IEV Delta (Δ) Tracking** using a lightweight local cache.
- **Logic:** 
    1. Every time `saham screen pre-open` is run, save the `{ticker: iev}` map to `.journals/.iev_delta.json`.
    2. On subsequent runs within the same morning, calculate `Delta = Current_IEV - Cached_IEV`.
- **UI:** Display a `ΔIEV` column with color-coding (Green for acceleration, Red for fading).

### Impact
Enables traders to identify "Late Accumulation" signals that are invisible in a single snapshot.

---

## 3. Workflow: Post-Open "Flash Validation" (`saham screen watch`)
**Category:** Execution Speed

### Observation
The current workflow has a "blind spot" at 09:00 AM. The user has the `ENTRY-RANGE` from the tool, but they must manually check their broker app to see if the *actual* opening price fell within that range.

### Contextual Edge (IHSG)
The first 5 minutes of IDX trading are the most chaotic. Manually validating 5+ candidates against their respective ranges is cognitively heavy and leads to "Analysis Paralysis" or missed entries.

### Recommendation
Introduce a new command: **`saham screen watch`**.
- **Logic:** This command reads the `.last-session.json` sidecar (from the pre-open run) and immediately attempts to fetch the *actual* opening prices for all candidates at 09:00:01 AM.
- **UI:** A simplified, high-visibility dashboard:
    - **BBCA:** OPEN 9,100 -> **[IN RANGE]** -> **ACTION: BUY**
    - **GOTO:** OPEN 250 -> **[OUTSIDE RANGE (GAP)]** -> **ACTION: SKIP**

### Impact
Automates the critical "Go/No-Go" decision, allowing the trader to focus exclusively on placing orders in their trading terminal.

---

## Summary of Implementation

| Feature | Technical Target | Intraday Edge |
| :--- | :--- | :--- |
| **ARA/ARB Metrics** | `domain/entities/price_limits.py` | Avoids "trapped" stocks; targets momentum limits. |
| **IEV Delta (Δ)** | `infrastructure/persistence/iev_cache.json` | Detects late-stage institutional entry. |
| **Flash Validation** | `adapters/cli/screen_commands.py (watch)` | Reduces 09:00 AM cognitive load for faster entry. |

---

## Implementation Status (Audit June 2026)

- **ARA/ARB Metrics:** **NOT MET.** Calculation of Auto-Rejection limits is not yet present in the `ScreenerCandidate` or Risk Engine.
- **IEV Delta (Δ) Tracking:** **NOT MET.** The `.iev_delta.json` cache and delta calculation logic are currently missing.
- **Flash Validation:** **MET.** Implemented as `saham intraday confirm-open`. This command realizes the goal of "Flash Validation" by grouping candidates into ENTER/WAIT/SKIP based on actual opening prices, reducing 09:00 AM cognitive load.

**Conclusion:**
Work on the intraday workflow has focused on the "Phase 2" execution logic (Confirm-Open). While safety guardrails (ARA/ARB) and velocity tracking (IEV Delta) are still pending, the core bottleneck of manual opening-price validation has been successfully solved.
