# ADR-022: IDX Regular Market Price Floor (Rp 50) Enforcements

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Implemented in the audited price-floor and sizing paths; new execution paths must reuse the canonical IDX rules.
**Decision**
Enforce the absolute Rp 50 regular market price floor in all pre-open and intraday trade calculations.

**Implications**

* Calculated stop losses are capped at Rp 50.
* Candidate pre-open screening must automatically filter out and skip tickers whose previous closing price is <= 50 or projected Indicative Equilibrium Price (IEP) <= 50.
* Ensure warning logs are generated when a candidate is excluded due to the price floor.

**Rationale**
Stocks trading at the Rp 50 floor price (e.g. GOTO) represent highly illiquid tickers ("gocian" stocks) with large seller queues and no committed buyers. Filtering them out at the start of the screening loop prevents the model from generating impossible stop-loss prices, preserves the mathematical validity of target risk-reward metrics, and reduces risk exposure to illiquid floor-locked assets.
