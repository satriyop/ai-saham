# ADR-007: Indicator Initialization & Warm-Up Policy

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned in indicator services; warm-up behavior must still be verified when adding an indicator.
**Decision**
Indicators must follow industry-standard initialization.

**Rules**

* No shortcut seeding (e.g., EMA first-price seed).
* SMA seed required where applicable.
* Indicators assume sufficient data.
* Warm-up handled in application/use-case layer.
* User-facing results exclude warm-up region.

**Rationale**
Matches TradingView / TA-Lib behavior and avoids start-point bias.
