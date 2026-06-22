# Antigravity Pre-Open Screener Tuning Diagnostic — 2026-06-22

This document details the quantitative session diagnostics and configuration calibration recommendations for the IDX pre-open learning loop based on the session run on **Monday, June 22, 2026**.

---

## 1. Session Metadata & Performance

* **Date:** 2026-06-22 (Monday)
* **Market Status:** Pre-Open (Regular sub-session resolved from Stockbit)
* **Tickers Evaluated:** 5 (`DSSA`, `GOTO`, `MAPI`, `BUKA`, `BBRI`)
* **Snapshot Phase:** `NCP_LOCKED` (08:57 WIB)

### Key Metrics Summary

| Metric | Target | Actual | Assessment |
| :--- | :--- | :--- | :--- |
| **Entry Range Hit Rate** | $100\%$ | **$100.0\%$** (5/5) | **Excellent.** Predicted entry boundaries match actual opening prices perfectly. |
| **IEP Mean Error** | $<1.5\%$ | **$0.925\%$** | **Excellent.** Low pre-market pricing noise. |
| **Trend Accuracy (T+5m)** | $>60\%$ | **$20.0\%$** (1/5) | **Failed.** Post-open momentum faded immediately. |
| **Trend Accuracy (T+30m)** | $>60\%$ | **$20.0\%$** (1/5) | **Failed.** Direction failed to hold through the session. |
| **Clean Trade Rate** | $>50\%$ | **$0.0\%$** (0/5) | **Failed.** No candidates reached the 1R profit target before stop. |

---

## 2. Quantitative Diagnostic Findings

1. **The "Gap & Fade" Regime:**
   The primary failure mode is immediate post-open momentum decay. While the screener predicted the entry ranges with absolute precision (100% hits, $<1\%$ pricing error), buying support evaporated within 5 minutes of the opening bell. 
   
2. **Profit Targets are Set Too Wide:**
   Even the strongest setup—**MAPI** (which registered excellent NCP-locked pre-open bid pressure of `0.975` and strong opening pressure of `0.74` at T0 and `0.75` at T5)—stalled and failed to reach the 1R target. This confirms that the current maximum ATR-scaled target boundaries are too wide to be achieved in this market regime.

3. **Pre-Open Noise Tickers:**
   * **DSSA** was marked WATCH despite having very low pre-open bid pressure (`0.145`) and negative momentum. It experienced a classic "gap and dump".
   * **GOTO** registered `0.0%` bid pressure at both T0 and T5, representing a dead-volume ticker that should have been filtered out entirely.

---

## 3. Recommended Config Calibrations

To complete the learning loop and optimize the pre-open screener for the current market conditions, update the following parameters in **[config/pre_open_screener.yaml](file:///Users/satriyo/dev/ai-saham/config/pre_open_screener.yaml)**:

```yaml
# Location: config/pre_open_screener.yaml

risk:
  # Increase min_target_ticks from 3 to 5.
  # Forces the model to require a larger initial upward thrust, filtering out
  # weak momentum plays that stall immediately after the open.
  min_target_ticks: 5

analysis:
  # Reduce atr_range_cap_max from 0.05 to 0.03 (5% to 3%).
  # Prevents entry ranges and targets from becoming too wide. Pulls the 1R
  # profit target closer to the entry range, making it achievable under current conditions.
  atr_range_cap_max: 0.03

  # Lower iev_intensity_unusual_threshold from 5.0 to 3.5.
  # Flags tickers with insufficient pre-open intensity earlier, moving dead-volume
  # tickers (like GOTO) to the SKIP list.
  iev_intensity_unusual_threshold: 3.5
```

---

## 4. Patterns to Watch for Next Session

* **Negative Bid Momentum:**
  If the next session continues to show high pre-open bid pressure followed by negative post-open bid momentum (`bp_momentum < 0`) resulting in 0% clean trades, we should introduce a hard gate requiring **positive bid momentum** (`bp_momentum > 0`) for any WATCH verdict to activate.
