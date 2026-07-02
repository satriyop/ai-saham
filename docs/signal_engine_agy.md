# Signal Engine Documentation

## 1. Purpose & Core Responsibility
The `SignalEngine` is a core application service designed to calculate a composite score and recommendation classification (STRONG, MODERATE, WEAK) for a stock ticker based on six distinct qualitative and quantitative factors. 

It is designed to evaluate a security's entry viability deterministically and operates on local-first principles.

---

## 2. Architecture & Layer Boundaries
The system strictly enforces Hexagonal Architecture boundaries:
* **Domain Layer ([signal_assessment.py](file:///Users/satriyo/dev/ai-saham/src/domain/value_objects/signal_assessment.py)):** Defines the output contract (enums like `SignalStrength` and `EntryQuality`), the immutable calculation result (`SignalAssessment`), and the pure input facts (`SignalContext`).
* **Application Layer ([signal_engine.py](file:///Users/satriyo/dev/ai-saham/src/application/services/signal_engine.py) & [assess_signal_use_case.py](file:///Users/satriyo/dev/ai-saham/src/application/use_case/assess_signal_use_case.py)):** Coordinates scoring weights and orchestration. Callers trigger evaluation via two entry points:
  * `evaluate()`: Self-fetches raw metrics from registered infrastructure ports (I/O path).
  * `evaluate_with_context()`: Executes a pure calculation pipeline using pre-loaded data. Used to prevent N+1 query performance degradation in bulk loops (e.g. screening 800+ tickers).
* **Infrastructure Layer:** Implements concrete database repositories and data provider ports (e.g., Bandar Detector, Analyst Consensus).
* **Adapter Layer:** wires the providers and handles commands (e.g., CLI parsing).

---

## 3. Data Source Inputs
The engine relies on six qualitative/quantitative inputs provided by concrete adapters:

| Factor | Source Port / Field | Normalized Scale | Default on Missing |
|---|---|:---:|:---:|
| **Bandar Intensity** | `BandarDetectorProvider` (`broad_score`) | 0 to 100 | `50.0` (Neutral) |
| **Foreign Flow Quality** | Screener Candidate Context (`foreign_flow_score`) | 0.0 to 100.0 | `50.0` (Neutral) |
| **Insider Activity** | `InsiderActivityProvider` (`insider_net_buy_ratio`) | 0.0 to 100.0 | `50.0` (Neutral) |
| **Seasonality Edge** | `SeasonalityProvider` (`win_rate_pct`, `avg_monthly_return_pct`) | 0.0 to 100.0 | `50.0` (Neutral) |
| **Analyst Consensus** | `AnalystConsensusProvider` (`buy_ratio`, `upside_pct`) | 0.0 to 100.0 | `50.0` (Neutral) |
| **Forward Valuation** | `ForwardEstimatesProvider` (`forward_pe`) | 0.0 to 100.0 | `50.0` (Neutral) |

---

## 4. Scoring Algorithm & Calculations

### Step A: Factor Normalization
Each input is normalized to a standard `0.0` to `100.0` range:

1. **Bandar Intensity:**
   * Maps a dynamic input range `[-max_range, +max_range]` linearly to `[0.0, 100.0]`.
   * Max range dynamically scales based on whether optional top-3, top-5, and top-10 accdist signals are present: `(3 + num_optional) * 2`.
2. **Foreign Flow Quality:**
   * Multiplies the raw pre-normalized `0.0` to `1.0` ratio by `100.0`.
3. **Insider Activity:**
   * Shifts net transaction buy ratio `[-1.0, +1.0]` (where `-1.0` is pure selling, `0.0` is neutral, and `+1.0` is pure buying) to `0.0` to `2.0` and multiplies by `50.0`.
4. **Seasonality Edge:**
   * **Tailwind** (average return > 0% AND monthly win rate > 50%): score = `win_rate_pct`.
   * **Headwind** (average return < 0% AND monthly win rate < 50%): score = `100.0 - win_rate_pct` *(see Section 5 for logic warning)*.
   * **Neutral:** score = `50.0`.
5. **Analyst Consensus:**
   * Sums points: `(buy_ratio * 60) + ((upside_pct / 30) * 40)`. Target upside capped at `30.0%`.
6. **Forward Valuation:**
   * Linearly interpolates the Forward P/E against four pricing tiers:
     * P/E <= 10: score = 95.0 (Very cheap)
     * P/E between 10 and 15: linear interpolation from 95.0 to 75.0
     * P/E between 15 and 20: linear interpolation from 75.0 to 50.0
     * P/E between 20 and 30: linear interpolation from 50.0 to 25.0
     * P/E > 30: decays toward 0.0 based on configured steps.

### Step B: Weighted Sum
The overall composite score is a weighted average of these six scores:
```
Score = (0.20 * Bandar) + (0.20 * ForeignFlow) + (0.20 * Insider) + (0.15 * Seasonality) + (0.15 * Analyst) + (0.10 * Valuation)
```

### Step C: Classification
The final rounded score [0, 100] determines quality:
* **Score >= 70:** STRONG strength -> ENTER entry quality.
* **Score >= 45:** MODERATE strength -> WATCH entry quality.
* **Score < 45:** WEAK strength -> AVOID entry quality.

### Step D: Market Context Post-Processing
If a `MarketContext` is provided (e.g. from `saham today` or screeners):
1. **Regime Multiplier:** The score is scaled down by the market regime multiplier (e.g. `x0.60` during `RISK_OFF`, `x0.50` during `VOLATILE`).
2. **Gate Tightening:** If active during negative regimes, any **ENTER** recommendation is automatically downgraded/capped to **WATCH**.

---

## 5. Identified Logic Smells & Recommendations
* **Seasonality Pattern Direction Check:**
  * **The Issue:** Under the current calculation, a strong headwind (e.g. win rate = 20%, indicating the stock historically falls 80% of the time in this month) yields a score of `100 - 20 = 80.0`. This gives the stock a high positive contribution to its bullish entry signal, despite seasonality being strongly bearish.
  * **Recommendation:** Bullish scoring should penalize bearish seasonality. Seasonal headwinds should scale down toward `0.0` (or below `50.0`), rather than mirroring tailwind scores. A future tuning cycle should adjust this formula.

---

## 6. Deep-Dive: Bandar Intensity Factor

### Concept & Market Microstructure
On the Indonesian Stock Exchange (IDX), transactions are processed via registered brokerages (identified by 2-letter codes like YP, CC, PD). By tracking the net transaction balance of these codes at the end of each session, we can identify institutional operator ("Bandar") footprints:
* **Top 1:** The single largest net-buying/net-selling broker.
* **Top 3:** The top 3 net-buying/net-selling brokers combined.
* **Top 5:** The top 5 net-buying/net-selling brokers combined.
* **Top 10:** The top 10 net-buying/net-selling brokers combined.

If buying is highly concentrated among the **Top 1/3/5** brokers while selling is fragmented across dozens of retail brokers, it indicates active institutional accumulation.

### Mapped Ordinal Scores
Each intensity label is assigned a numeric value:
* `"Big Acc"` -> +2
* `"Small Acc"` -> +1
* `"Neutral"` -> 0
* `"Small Dist"` -> -1
* `"Big Dist"` -> -2

### Dynamic Range Calculation
The `broad_score` is a simple sum of these values across all available signals. Because some tickers or days lack optional top-3/5/10 records, the range is dynamic:
* **Mandatory inputs (3):** `today_accdist`, `five_day_accdist`, and `top1_accdist` (base range is `[-6, +6]`).
* **Optional inputs (up to 3):** `top3_accdist`, `top5_accdist`, and `top10_accdist` (if populated).
* **Formula:**
```
max_range = (3 + num_optional) * 2
```

### Final Factor Normalization
The resulting raw `broad_score` is scaled to a standard 0 to 100 point score:
```
Score = ((broad_score + max_range) / (2 * max_range)) * 100.0
```

---

## 7. Deep-Dive: Foreign Flow Quality Factor

### Concept & Market Microstructure
Foreign institutional desks (often referred to simply as "Foreign Flow") act as major directional catalysts for IDX securities. This factor evaluates the intensity, persistence, and technical context of foreign broker transactions.

The calculation evaluates **seven sub-components**, summing up to a maximum raw score of **120.0 points**:

```
RawScore = Consistency + Streak + VWAP_Discount + RSI_Headroom + Flow_Ratio + BB_Squeeze + BCI_Points
```

### Sub-Component Breakdown
1. **Consistency (Weight: 40.0):**
   * Uses `net_buy_ratio` (percentage of days in the lookback window where foreign net buy value was positive).
   * Formula: `net_buy_ratio * 40.0`.
2. **Streak (Weight: 30.0):**
   * Rewards consecutive buying days using an exponential saturation decay:
   * Formula: `30.0 * (1.0 - exp(-streak / 7.0))` (where 7.0 is the decay constant).
3. **VWAP Discount (Weight: 20.0):**
   * Measures if the current close price is trading below the average price foreign operators bought at (`vwap_discount_pct`).
   * Saturated at a 10% discount.
   * Formula: `(vwap_discount_pct / 10.0) * 20.0` (capped).
4. **RSI Headroom (Weight: 10.0):**
   * Evaluates if there is technical room to run (avoids buying overbought stocks).
   * Scores highest at a neutral RSI of 40.0, scaling down to 0 at RSI <= 25 or >= 75.
5. **Foreign Flow Ratio (Weight: 10.0):**
   * Measures how much of the daily stock turnover is foreign-led.
   * Saturated at a 20% foreign turnover share.
   * Formula: `(avg_flow_ratio / 20.0) * 10.0` (capped).
6. **Bollinger Band Squeeze (Weight: 10.0):**
   * Rewards price volatility contraction (Bollinger Band Width percentile vs. past 60 days).
   * Maximum points given when BB width is in the bottom 20% percentile (tight squeeze).
7. **Broker Concentration Index (BCI) (Weight: 15.0 max):**
   * Detects if institutional-grade foreign brokers are clustered:
     * Label `"CLUSTER"` (high concentration of Tier 1 foreign desks) -> 15.0 points.
     * Label `"STABLE"` (moderate concentration) -> 5.0 points.
     * Retail-led -> 0.0 points.

### Final Factor Normalization
Once the raw score [0.0, 120.0] is summed, the `SignalEngine` normalizes it to a 0 to 100 point scale:
```
Score = (RawScore / 120.0) * 100.0
```

---

## 8. Architectural Perspective: Composite of Composites

### Vetting the Aggregation Pattern
The Foreign Flow Quality factor is structurally a **composite of composites** (a double-level aggregation). 

This is a valid and robust pattern for quantitative engines, serving specific architectural purposes:
* **Dimensionality Reduction:** Instead of forcing the top-level Signal Engine to balance 15+ flat weights, related sub-metrics are encapsulated inside the Foreign Flow domain model. This allows top-level configuration weights to stay clean and readable (e.g. 20% Bandar, 20% Foreign Flow, etc.).
* **Modularity and Reuse:** The `ScoreForeignFlowUseCase` is decoupled from the rest of the engine. Other workflows (such as the Swing Screener) can fetch and filter candidates based purely on raw `foreign_flow_score` without loading valuation, consensus, or seasonality dependencies.
* **Collinearity Safeguard:** Double-counting technical indicators is avoided. While the Foreign Flow sub-composite uses **RSI** and **Bollinger Bands**, the top-level Signal Engine does not have another competing technical momentum factor. The other 5 dimensions are non-overlapping (Valuation, Insider, Seasonality, Bandar, Analysts).

---

## 9. Deep-Dive: Insider Activity Factor

### Concept & Market Microstructure
Corporate insiders (Directors, Commissioners, and Major Shareholders) possess intimate operational knowledge of their firms. While selling can happen for many non-fundamental reasons (such as portfolio rebalancing, taxes, or liquidity needs), insider buying is historically a high-conviction vote of confidence.

The `SignalEngine` tracks these transactions over a **lookback window** (default: `90` days) using official disclosures collected from IDX disclosures.

### Share-Weighted Net Buy Ratio
The factor calculates the total shares transacted by insiders:
```
total_shares = buy_shares + sell_shares
```

Then it computes the net buy ratio:
```
net_buy_ratio = (buy_shares - sell_shares) / total_shares
```

This yields a value in the range of `[-1.0, +1.0]`:
* `+1.0`: 100% of insider transacted volume was buying.
* `-1.0`: 100% of insider transacted volume was selling.
* `0.0`: Mapped net volume of buys and sells was equal.
* `None`: No transactions were recorded in the window (falls back to neutral 50.0).

### Factor Normalization
If the ratio is not `None`, it is scaled to the 0 to 100 point score:
```
Score = ((net_buy_ratio + 1.0) / 2.0) * 100.0
```

### Key Design Assumptions & Implications
* **Share-Weighting vs. Headcount:** The score is volume-weighted, not transaction-count-weighted. If 5 directors buy 10,000 shares each (5 bullish events), but 1 major holder sells 200,000 shares (1 bearish event), the net buy ratio is negative (`-0.60` -> `20.0` points). The single large transaction overrides the others under the assumption that size reflects conviction.
* **No Role-Weighting:** Directors (`DIREKTUR`), Commissioners (`KOMISARIS`), and Major Holders (`MAJOR_HOLDER`) are weighted identically per share. A routine rebalancing sale by a large holder can wipe out a highly bullish buy signal from the Managing Director.
* **Share Count vs. Cash (IDR) Value:** The score is based purely on transacted shares rather than total Rupiah value.
* **Neutral Default:** A lack of insider activity yields `None` which defaults to `50.0` points. Insiders not trading does not penalize the security.

