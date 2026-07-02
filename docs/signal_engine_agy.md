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
  * `evaluate_with_context()`: Executes a pure calculation pipeline using pre-loaded data. Used to prevent $N+1$ query performance degradation in bulk loops (e.g. screening 800+ tickers).
* **Infrastructure Layer:** Implements concrete database repositories and data provider ports (e.g., Bandar Detector, Analyst Consensus).
* **Adapter Layer:** wires the providers and handles commands (e.g., CLI parsing).

---

## 3. Data Source Inputs
The engine relies on six qualitative/quantitative inputs provided by concrete adapters:

| Factor | Source Port / Field | Normalized Scale | Default on Missing |
|---|---|:---:|:---:|
| **Bandar Intensity** | `BandarDetectorProvider` (`broad_score`) | Dynamic $0$–$100$ | `50.0` (Neutral) |
| **Foreign Flow Quality** | Screener Candidate Context (`foreign_flow_score`) | $0.0$–$100.0$ | `50.0` (Neutral) |
| **Insider Activity** | `InsiderActivityProvider` (`insider_net_buy_ratio`) | $0.0$–$100.0$ | `50.0` (Neutral) |
| **Seasonality Edge** | `SeasonalityProvider` (`win_rate_pct`, `avg_monthly_return_pct`) | $0.0$–$100.0$ | `50.0` (Neutral) |
| **Analyst Consensus** | `AnalystConsensusProvider` (`buy_ratio`, `upside_pct`) | $0.0$–$100.0$ | `50.0` (Neutral) |
| **Forward Valuation** | `ForwardEstimatesProvider` (`forward_pe`) | $0.0$–$100.0$ | `50.0` (Neutral) |

---

## 4. Scoring Algorithm & Calculations

### Step A: Factor Normalization
Each input is normalized to a standard `0.0`–`100.0` range:

1. **Bandar Intensity:**
   * Maps a dynamic input range `[-max_range, +max_range]` linearly to `[0.0, 100.0]`.
   * Max range dynamically scales based on whether optional top-3, top-5, and top-10 accdist signals are present: `(3 + num_optional) * 2`.
2. **Foreign Flow Quality:**
   * Multiplies the raw pre-normalized `0.0`–`1.0` ratio by `100.0`.
3. **Insider Activity:**
   * Shifts net transaction buy ratio `[-1.0, +1.0]` (where `-1.0` is pure selling, `0.0` is neutral, and `+1.0` is pure buying) to `0.0`–`2.0` and multiplies by `50.0`.
4. **Seasonality Edge:**
   * **Tailwind** (average return > 0% AND monthly win rate > 50%): score = `win_rate_pct`.
   * **Headwind** (average return < 0% AND monthly win rate < 50%): score = `100.0 - win_rate_pct` *(see Section 5 for logic warning)*.
   * **Neutral:** score = `50.0`.
5. **Analyst Consensus:**
   * Sums points: `(buy_ratio * 60) + ((upside_pct / 30) * 40)`. Target upside capped at `30.0%`.
6. **Forward Valuation:**
   * Linearly interpolates the Forward P/E against four pricing tiers:
     * $P/E \le 10 \rightarrow 95.0$ (Very cheap)
     * $P/E \in [10, 15] \rightarrow 95.0 \rightarrow 75.0$
     * $P/E \in [15, 20] \rightarrow 75.0 \rightarrow 50.0$
     * $P/E \in [20, 30] \rightarrow 50.0 \rightarrow 25.0$
     * $P/E > 30 \rightarrow$ Decays toward `0.0` with a configured step decay.

### Step B: Weighted Sum
The overall composite score is a weighted average of these six scores:
$$\text{Score} = (0.20 \times \text{Bandar}) + (0.20 \times \text{ForeignFlow}) + (0.20 \times \text{Insider}) + (0.15 \times \text{Seasonality}) + (0.15 \times \text{Analyst}) + (0.10 \times \text{Valuation})$$

### Step C: Classification
The final rounded score $[0, 100]$ determines quality:
* **Score $\ge 70$:** **STRONG** strength $\rightarrow$ **ENTER** entry quality.
* **Score $\ge 45$:** **MODERATE** strength $\rightarrow$ **WATCH** entry quality.
* **Score $< 45$:** **WEAK** strength $\rightarrow$ **AVOID** entry quality.

### Step D: Market Context Post-Processing
If a `MarketContext` is provided (e.g. from `saham today` or screeners):
1. **Regime Multiplier:** The score is scaled down by the market regime multiplier (e.g. `x0.60` during `RISK_OFF`, `x0.50` during `VOLATILE`).
2. **Gate Tightening:** If active during negative regimes, any **ENTER** recommendation is automatically downgraded/capped to **WATCH**.

---

## 5. Identified Logic Smells & Recommendations
* **Seasonality Pattern Direction Check:**
  * **The Issue:** Under the current calculation, a strong headwind (e.g. win rate = 20%, indicating the stock historically falls 80% of the time in this month) yields a score of `100 - 20 = 80.0`. This gives the stock a high positive contribution to its bullish entry signal, despite seasonality being strongly bearish.
  * **Recommendation:** Bullish scoring should penalize bearish seasonality. Seasonal headwinds should scale down toward `0.0` (or below `50.0`), rather than mirroring tailwind scores. A future tuning cycle should adjust this formula.
