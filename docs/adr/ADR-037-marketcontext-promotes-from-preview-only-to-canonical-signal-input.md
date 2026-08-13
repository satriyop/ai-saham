# ADR-037: MarketContext Promotes from Preview-Only to Canonical Signal Input

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted — supersedes ADR-032 signal-preview constraint; **surface scope
amended by [ADR-054](ADR-054-screen-judge-plan-structure-contract.md) Policy A and
[ADR-057](ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md)**
**Date:** 2026-07-03
**Current implementation:** Regime conditioning of the canonical signal remains a
valid **engine** capability when a path supplies `market_context` into
`AssessSignalEvidenceUseCase`. **Primary live desks do not use that path today:**
`screen accum` / plan-structure Policy A treat MCE as **display-only diagnostic
evidence** (ADR-054/057); plan does not recompute Action via MCE. Risk-side
regime adjustment remains preview-only everywhere.

### Context

ADR-032 designated `--with-market-context` as preview/enrichment only: "it does not change the
canonical `TradeSetup`." That was the correct constraint in June 2026 when MCE thresholds were
uncalibrated and regime parameters were not yet config-backed.

Phase 5 of the SignalEngine staged-evidence refactor completes the missing calibration
prerequisites:

- Regime conditioning is fully config-backed (`config/signal_engine.yaml:
  signal_engine.regime_conditioning.*`).
- Conditioning is deterministic and auditable: notes appear in `rationale`, markers appear in
  `breakdown`, visible in `--diagnostic`.
- Conditioning is applied BEFORE group renormalization (not as a blunt post-score scalar
  multiply), making it semantically precise: RISK_OFF discounts weak setup evidence (PARTIAL/
  NO_MATCH tier); NEUTRAL discounts weak flow; VOLATILE applies general discounts to both groups.
- `gate_tightening` (ENTER→WATCH cap) is exposed as a per-`MarketContext` field, independently
  configurable from score discounts.

### Decision

When `--with-market-context` is enabled, `MarketContext` is now an explicit evidence conditioning
input to `AssessSignalEvidenceUseCase`, not a post-score adjustment. This means:

1. **The canonical signal score IS affected by regime conditioning** when
   `--with-market-context` is supplied. Canonical `TradeSetup` action may differ with vs without
   MCE.

2. **`market_context_signal_preview` is now the same object as `signal_assessment`** (the
   canonical regime-conditioned signal). The preview/delta concept for the signal no longer
   applies — the signal itself IS the regime-conditioned signal. The MCE preview panel remains
   meaningful for the *risk* side: `market_context_risk_preview` and
   `market_context_trade_setup_preview` still show the what-if effect of regime-adjusted risk gates.

3. **The `--with-market-context` flag remains optional and off-by-default.** Without it,
   `market_regime=None` is passed to the signal use case, which applies no conditioning.
   The system remains fully functional without MCE.

4. **ADR-032's preview-only constraint is superseded for signal only.** Risk-side preview
   (regime-adjusted gates) remains a preview; it does not change `risk_response` (the canonical
   risk assessment). Only the canonical signal score is now regime-influenced.

### Boundary

```
--with-market-context present:
  market_regime → AssessSignalEvidenceRequest.market_context
      → regime conditioning applied to group scores (canonical)
      → gate_tightening cap applied (canonical)
  canonical TradeSetup = f(regime-conditioned signal, canonical risk)
  MCE preview TradeSetup = f(same signal, regime-adjusted risk preview)

--with-market-context absent:
  market_regime = None → no conditioning → identical to pre-Phase-5 behavior
```

### Consequences

- The CLI display "Signal impact" line in the MARKET CONTEXT PREVIEW panel is retired (signal
  preview == canonical signal; no delta to show). The panel remains for the risk preview and
  TradeSetup action preview.
- The panel subtitle is updated from "evidence only — does not change final TradeSetup" to
  "regime conditioning in canonical signal · risk preview via MCE".
- The workflow test `test_swing_workflow_canonical_trade_setup_unaffected_by_market_context`
  is retired; the new contract is "regime conditioning is forwarded to signal engine when
  market_context is supplied."

### Learning Loop Note

MCE thresholds (weak_flow_threshold, weak_setup_threshold, discounts) are now config-backed
and tunable via `config/signal_engine.yaml` without code changes. Calibration of these values
uses the current guarded policy / research workflow (see ADR-049 and live `saham --help`);
do not assume a retired `trade tune signal` path.

### Amendment — surface Policy A (ADR-054 / ADR-057)

This ADR's Decision still describes the **engine contract** when a caller wires
`market_context` into signal assessment. It does **not** authorize every CLI/TUI
surface to do that wiring.

| Surface | MCE role after ADR-054 Policy A |
|---|---|
| `screen accum` (universe + ticker) | **Diagnostic / display-only** panel; must not change Action via MCE |
| `plan swing` | Structure-only product job; **no** Action recompute via MCE / TechnicalGate |
| Engine path that explicitly passes `market_context` | May condition signal (this ADR) — only if a future task promotes B-MCE into DecisionPolicy |

Agents must not read Decision §1–2 as “screen/plan Action moves with MCE.”
Read ADR-054 Policy A and ADR-057 for live-desk authority.
