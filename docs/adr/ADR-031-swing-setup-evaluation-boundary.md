# ADR-031: Swing Setup Evaluation Boundary

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted
**Date:** 2026-06-25
**Current implementation:** Setup evaluation remains evidence about setup fit and entry authority; it does not independently replace the composed `TradeSetup` verdict.

### Context

The swing workflow previously exposed `--preset foreign-bounce` and returned a setup-like result using `ENTER`, `WATCH`, and `AVOID`. That duplicated final-action vocabulary already owned by `TradeSetup` (ADR-026), and the foreign-bounce gate policy lived in the CLI adapter.

### Decision

Rename the concept from **preset** to **setup** and make setup evaluation an application-layer deterministic policy.

Setup evaluation answers only:

> Does this candidate fit the named setup?

Setup evaluation returns:

| Result | Meaning |
|--------|---------|
| `MATCH` | All setup gates pass |
| `PARTIAL` | Candidate is close enough to track, but at least one gate failed |
| `NO_MATCH` | Candidate does not fit the setup |

Final trading action remains exclusively owned by `TradeSetup.action` (`ENTER`, `WATCH`, `AVOID`, `BLOCKED_EXECUTION`, `BLOCKED_STRUCTURAL`).

The initial setup catalog is:

| Setup | Question Answered | Required Evidence |
|-------|-------------------|-------------------|
| `foreign-bounce` | Is foreign accumulation happening while price is still below foreign VWAP in a range? | accumulation candidate |
| `coiled-spring` | Is accumulation happening while volatility is compressed enough for a potential expansion? | accumulation candidate with BB width percentile |
| `smart-money-confirmed` | Is broker attribution led by smart-money flow rather than noise flow? | accumulation candidate plus broker-detail attribution |
| `pullback-continuation` | Is an uptrend pullback still supported by foreign flow and RSI headroom? | accumulation candidate |

All setup gate thresholds and enable flags must be configurable through `config/swing_setups.yaml`. Code-level defaults are deterministic fallbacks only. Calibration and future learning should propose YAML changes, not code edits.

### Layer Plan

| Layer | Artifact |
|-------|----------|
| Domain | `SetupEvaluation`, `SetupGate`, `SetupMatch` value objects |
| Application | `EvaluateSwingSetupUseCase` for named setup policy |
| Infrastructure | `config/swing_setups.yaml` setup gates; `config/swing_targets.yaml` regime TP/SL targets |
| Adapter | CLI `--setup`, setup JSON/display formatting only |

### Rationale

Setup evaluation is not a first-class engine like SignalEngine, RiskEngine, or MarketContextEngine. It is a named pattern-fit check for a workflow. Making it an engine would overstate its scope and duplicate orchestration boundaries.

Keeping setup policy in application code satisfies adapter thinness: CLI adapters parse `--setup`, wire dependencies, and format results; they do not own gate policy or business classification.

### Compatibility

This is a breaking rename. Public CLI flags, JSON fields, and journal fields use:

| Old | New |
|-----|-----|
| `--preset` | `--setup` |
| JSON `preset` | JSON `setup` |
| journal `preset` | journal `setup` |
| journal `classification` | journal `setup_match` |

### Setup Entry Authority Metadata

Each setup in `config/swing_setups.yaml` must declare:

| Field | Purpose |
|-------|---------|
| `family` | Canonical setup family used for target filter matching |
| `entry_authority` | Whether this setup may independently produce `ENTER` |
| `can_enter_from_phases` | Setup phases that satisfy the entry authority gate |

`SetupEvaluation` remains pattern-fit evidence only — it answers "does this candidate fit the named setup?" and returns `MATCH`/`PARTIAL`/`NO_MATCH`. It does not decide final action.

`DecisionPolicy` consumes `entry_authority` metadata from the resolved setup configuration. A setup with `entry_authority: false` (e.g. `smart-money-confirmed`) cannot independently create `ENTER` even if `SetupEvaluation` returns `MATCH`. Such setups may contribute evidence, rationale, or conviction to the final verdict, but the final action remains the exclusive responsibility of `SignalEngine + DecisionPolicy -> TradeSetup`.

This ensures that confirmation-only patterns complement the decision without bypassing the authority chain.
