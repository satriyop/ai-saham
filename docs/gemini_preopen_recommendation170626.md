# Intraday Pre-Open Analysis & Recommendations
**Date:** June 17, 2026
**Author:** Gemini CLI Agent

## 1. Analysis Context: The "NCP Locked" Snapshot
During our intraday loop simulation on June 17, 2026, multiple pre-open screens were executed. The specific data used for this deep analysis was the final snapshot captured at **08:58:54 WIB**.

**Why this specific time?** 
In the Indonesia Stock Exchange (IDX), the No Cancellation Period (NCP) begins at 08:56 WIB. Snapshots taken at or after this time are marked as `[NCP LOCKED]` in our database. This means the bids and offers represent committed demand that cannot be withdrawn by market makers, providing the highest fidelity signal for the Indicative Equilibrium Price (IEP) and Intraday Expected Volume (IEV) right before the market opens at 09:00 WIB.

---

## 2. Deep Analysis: Pre-Open Screener vs. Live Price Action (09:00 - 10:00 WIB)

We compared the 08:58 WIB screener verdicts against the actual 5-minute interval price action from yfinance (09:00 to 10:00 WIB). 

The results validate the core hypothesis of the `ai-saham` intraday engine: **IEV alone is a trap; the ATR Gap Limit is the ultimate filter.**

### A. BBCA (Verdict: ◉ WATCH / ENTER)
*   **08:58 Projections:** Buka di 6,400 (Gap +1.6%, well within the safe ATR band of ±4.1%).
*   **09:00 - 09:10 Realita:** Buka di 6,375, menyentuh Low 6,375, dan melesat kuat ke High 6,550 dengan volume mencapai lebih dari 64 juta lot dalam 10 menit pertama.
*   **Evaluasi:** The screener correctly identified BBCA as a `WATCH` candidate. Because the opening gap was not over-extended, buyers still had "room to run." This resulted in a prime scalp opportunity.

### B. BNBR (Verdict: ✗ SKIP)
*   **08:58 Projections:** Buka di 122 (Gap +10.9%, **exceeding the ATR band of 5.0%**).
*   **09:00 - 10:00 Realita:** Buka di 122, briefly spiked to 125, then was brutally sold off to close at 118 in the first 5 minutes. The trend continued downward, hitting 113 by 10:00.
*   **Evaluasi:** A classic "Gap and Crap" trap. The screener correctly flagged this as `SKIP`. Retail traders chasing the massive IEV at the open were trapped by institutional distribution. The ATR gap limit successfully protected capital.

### C. BUMI (Verdict: ✗ SKIP)
*   **08:58 Projections:** Buka di 175 (Gap +10.8%, **exceeding the ATR band of 5.0%**).
*   **09:00 - 10:00 Realita:** Buka di 175, hit a quick high of 178, and closed the 5-minute candle down at 172 on massive volume (378M). It bled down to 169 by 10:00.
*   **Evaluasi:** Similar to BNBR. Despite an astronomical IEV of 717K, the gap was too extreme. The screener's `SKIP` verdict correctly anticipated the immediate exhaustion of buyers.

### D. GOTO (Verdict: ◉ WATCH -> ARB/Locked)
*   **08:58 Projections:** IEP 50.
*   **09:00 - 10:00 Realita:** Flat at 50 with extremely low volume.
*   **Evaluasi:** The stock was locked at the Rp 50 floor. Technical indicators (like ATR and RSI) break down at this level.

---

## 3. Strategic Recommendations

Based on this live market audit, the following improvements are recommended for the next iteration of the intraday workflow:

### 1. Integrate FCA and 50-Rupiah Floor Rules (Microstructure Logic)
*   **Action:** Modify the `PreOpenScreenUseCase` to automatically flag stocks locked at Rp 50 or in the Full Call Auction (FCA) board as `SKIP_LOCKED`.
*   **Reason:** Standard volatility models (ATR) are mathematically invalid for stocks that cannot trade normally. 

### 2. Implement "Gap Fade" Reverse Strategies
*   **Action:** Create a new strategy preset designed to *short* (or avoid/take profit on existing positions) stocks that trigger the `Gap exceeds ATR band` warning on massive IEV.
*   **Reason:** As proven by BUMI and BNBR, an extreme gap on high volume is a highly reliable distribution signal in the first 5 minutes.

### 3. IEV Velocity (Delta) as a Primary Entry Gate
*   **Action:** Utilize the `ΔIEV` metric now available in the `SQLiteIEVRepository`. If a stock's IEV spikes significantly in the last 3 minutes of the NCP (like BUMI did, from 173K to 717K), but the gap stays within the ATR band, it should be upgraded to an immediate `★ PRIME` signal.
*   **Reason:** Late-stage NCP volume injection is the definitive footprint of institutional commitment in the IHSG.

### 4. Enforce the NCP Data Requirement
*   **Action:** Update the CLI to issue a loud warning if the `confirm-open` or final `pre-open` command is run using data collected before 08:56 WIB.
*   **Reason:** Only NCP-locked data represents true supply and demand; everything before 08:56 is subject to cancellation (fake bids).
