# ADR-053: Sector Macro Context Evidence (routed per-sector macro drivers)

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — S1–S3 + multi-map/P2a bank BI steps shipped
(DIAGNOSTIC; schema v9 fingerprints). S4 attribution still open.
**Date:** 2026-07-28
**Depends on:** [ADR-009](ADR-009-config-driven-behavior.md),
[ADR-029](ADR-029-market-context-engine-mce-third-first-class-application-service.md),
[ADR-041](ADR-041-canonical-signal-evidence-input-boundary.md)
**Related:** peer-relative `SectorContextEvidence` (Phase H),
`TickerProfile` diagnostics, MCE optional `commodity_composite`,
[ADR-054](ADR-054-screen-judge-plan-structure-contract.md) (panel on judgment desk),
[ADR-055](ADR-055-macro-calendar-fetch.md) (BI policy spine)

## Context

The system already answers three different context questions:

| Layer | Artifact | Question |
|-------|----------|----------|
| Market-wide | `MarketContextEngine` → `MarketContext` | Is the broad environment risk-on / risk-off / volatile? |
| Sector peers | `SectorContextEvidence` | How are same-sector peers trading vs IHSG and vs this ticker? |
| Ticker style | `TickerProfile` | How does this name typically trade (foreign / bandar / retail)? |

None of those answers: **for this sector, which external macros should an analyst
watch?** Example: energy names are more sensitive to coal/commodity and FX moves
than to generic peer breadth alone.

MCE already defines an optional global `commodity_composite` (CPO + coal,
**disabled by default**). That factor, when enabled, would reweight **every**
ticker’s market regime. It does not route drivers by sector. Hardcoding
“if energy then oil” in adapters would violate config-driven and thin-adapter
rules.

## Decision

Introduce **Sector Macro Context** as a **separate diagnostic evidence family**,
sibling to peer-relative sector context — not a second MCE and not a silent
score rewrite.

### 1. Name and identity

| Item | Value |
|------|--------|
| Product / type name | `SectorMacroContext` / `SectorMacroContextEvidence` |
| Config path | `config/sector_macro_context.yaml` |
| Fingerprint field prefix | `smc_*` |
| Authority (v1) | `DIAGNOSTIC` only |

“Overlay” may appear in prose; it is **not** the type or config stem.

### 2. Three-layer context model (locked)

```text
L1  MarketContext              market-wide regime (authoritative when requested)
L2a SectorContextEvidence      peer technicals (DIAGNOSTIC)
L2b SectorMacroContextEvidence routed macro drivers (DIAGNOSTIC)  ← this ADR
L3  TickerProfile              participant / liquidity style (DIAGNOSTIC)
```

L2a and L2b answer different questions and **must remain separate VOs**.

### 3. Sector key source

**Primary key:** `universes.yaml` **group name**, resolved the same way peer
sector context already does (`sector_group_for_ticker` / reverse index of
non-index universe groups).

Examples: `energy`, `bank`, `basic_materials`.

**Rejected as primary keys for v1:**

- Free-text `StockMeta.sector` labels (drift / localization)
- Yahoo `StockMeta.sector_key` as the sole map key (external taxonomy, sparse for IDX)

**Optional later (not v1):** explicit alias table
`yahoo_sector_key → universe_group` for enrichment only.

Ticker with no matching universe group → deterministic
`SectorMacroContextEvidence.unavailable(...)` / `macro_regime=UNKNOWN`.

### 4. Config shape (intent)

Config owns:

1. A **factor library** (series identity, return kind, thresholds, optional invert)
2. **Sector maps** (universe group → weighted refs into the library)
3. Coverage / lookback / evidence_status defaults

Builders must not hardcode sector→series routing. Adapters must not own policy.

### 5. v1 live scope

| Concern | Decision |
|---------|----------|
| Config multi-map ready | Yes from day one |
| Live sector maps | commodity/BM/consumer + `property_dev`/`telco`/`poultry` + `insurance`/`multifinance`/`packaging` + `bank`/`logistics` |
| Live series | oil: `CL=F`; soft: `CPO=F`; metals: `HG=F`; gold: `GC=F`; feed: `ZC=F`+`ZS=F` (invert); FX risk: `IDR=X` (invert); domestic rates: virtual `BI_RATE` via macro calendar. `^TNX` remains in library only (not on live maps after Track B) |
| Dedicated groups | most maps use dedicated cohorts; `insurance`/`logistics`/`bank` reuse existing universe keys |
| Poultry policy | Feed-cost stress (corn+soy invert) + import FX (`usd_idr_risk`); not chicken-price model (P1c) |
| Domestic rates maps (Track B) | `bank`, `cement`, `property_dev`, `telco`, `insurance`, `multifinance` share defensive **BI policy steps + `usd_idr_risk`** (not US 10Y) |
| Coverage expansion (Track C) | Residual `property` (same as property_dev); `transportation` (oil_cost+IDR like logistics); dedicated `auto` cohort (BI+IDR; includes ASII); residual `consumer_goods` / `consumer_non_cyclicals` / `consumer_staples` (BI+IDR). **Not** mapped: full `cyclic`, `tech`, `health` (no honest ≥2 drivers yet) |
| Oil sign split (P1a) | `oil_proxy` (↑ supportive) for energy/oil_gas; `oil_cost` (↑ headwind) for chemicals/logistics/packaging |
| Energy purity (P1b) | `coal` (COAL ETF proxy + IDR) and `oil_gas` (CL=F + IDR) preferred over residual `energy` map; parent energy bag kept |
| Bank / rates policy (P2a+B) | Defensive: BI `policy_rate_steps` (hike = headwind) + `usd_idr_risk`; not NIM expansion. Stockbit title **Interest Rate Decision** → `bi_rate` (facility rates excluded) |
| Dead Yahoo symbols (do not map live) | `MTF=F` (API2/Newcastle alt — no usable OHLCV bars), `KO=F` (legacy CPO — HTTP 404) as of 2026-07 smoke |
| Series quality (Track DQ-1) | **Liquid cores:** `CL=F`, `IDR=X` (FX vol often 0 — expected), grains `ZC=F`/`ZS=F`, metals `HG=F`/`GC=F`. **Coal:** `COAL` ETF is a live basket proxy, not Newcastle FOB. **Palm:** `CPO=F` is thin ALTSYMBOL (mostly zero volume); still used for DIAGNOSTIC plantation returns until a better feed exists. Do not map `ZL=F` soy oil as palm without an explicit product decision. Full notes: `docs/data_sources.md` § Sector macro series quality |
| Thin multi-sector maps (e.g. banks → 100% USDIDR) | **Forbidden** |
| Auto-fetch | Live-map series refresh on every `saham fetch market` (`sector_macro` context labels) |

### 6. Output contract (intent)

`SectorMacroContextEvidence` (frozen) carries at least:

- `sector_group` (universe group key)
- `as_of_date`
- Per-factor scores: series, raw value, score 0–1 or None, weight, label, rationale
- `composite_score` (renormalized over available factors) or None
- `macro_regime`: `SUPPORTIVE | NEUTRAL | HEADWIND | UNKNOWN`
- `coverage_score`
- `evidence_status` (DIAGNOSTIC in v1)
- reasons / unavailable_reasons / metadata

**Vocabulary is intentionally distinct** from market and peer regimes:

| Layer | Labels | Meaning |
|-------|--------|---------|
| Market (`MarketContext`) | RISK_ON / NEUTRAL / RISK_OFF / VOLATILE | Broad risk appetite |
| Sector peers | BULLISH / NEUTRAL / BEARISH / UNKNOWN | Peer technicals vs IHSG |
| Sector macro | SUPPORTIVE / NEUTRAL / HEADWIND / UNKNOWN | External drivers for this sector |

Do not reuse `RISK_ON` or `BULLISH` for sector macro labels.

### 7. Runtime and layer boundaries

```text
Workflow / use case loads series candles (fetch-or-cache owned by application)
        → SectorMacroContextEvidenceBuilder (pure; no IO; never raises)
        → evidence bundle / fingerprint / CLI display
```

| Layer | Responsibility |
|-------|----------------|
| Domain | `SectorMacroContextEvidence` (+ factor score VOs); pure validation |
| Application | Builder + request DTO; orchestration that supplies candles and sector group |
| Infrastructure | YAML loader; universe reverse index reuse; series fetch via existing market-data path |
| Adapter | Thin display panel; no sector→series policy |

**Offline-first:** builder never fetches. Missing series → factor UNAVAILABLE,
not crash. Low coverage → `UNKNOWN` when below configured threshold.

### 8. Relationship to MCE `commodity_composite`

| Path | Role |
|------|------|
| MCE `commodity_composite` | Optional **global** market factor (still `enabled: false` unless separately decided) |
| Sector macro | **Routed** per-sector drivers |

**This ADR does not enable** MCE `commodity_composite`. Enabling it remains a
separate product decision because it would reweight market regime for all
tickers. The two paths must not share a score path in v1.

### 9. Authority and promotion

**v1 (this ADR):**

- DIAGNOSTIC only
- Persist on observation fingerprint for replay / attribution
- Display in plan/detail surfaces
- **Must not** multiply canonical signal score
- **Must not** set RiskEngine `gate_tightening`
- **Must not** create ENTER or loosen ENTER caps
- **Must not** silently rewrite setup evidence

**Promotion (future ADR required):**

- Walk-forward attribution (e.g. does HEADWIND reduce outcomes for energy names?)
- Explicit authority bump (e.g. LOW_WEIGHT slot, confidence cap, or eligibility note)
- Same validator / out-of-sample guardrails as other evidence families (ADR-041 lineage)

Diagnostic status alone never grants DecisionPolicy authority.

### 10. Delivery slices (implementation guidance)

| Slice | Deliverable |
|-------|-------------|
| S0 | This ADR + index (done) |
| S1 | Domain VO + config schema + pure builder + unit tests |
| S2 | Wire into swing/screen evidence assembler + fingerprint fields |
| S3 | CLI panel + live `energy` map with `MTF=F` + `IDR=X` |
| S4 | Research / attribution hooks only (no promotion) |

## Invariants

1. Sector macro is **not** a second `MarketContextEngine`.
2. Peer sector context (L2a) and sector macro (L2b) remain separate.
3. Universe group key is the primary sector identity for maps.
4. Config owns routing; adapters stay thin.
5. Builder is pure, fail-soft, offline-capable with preloaded series.
6. v1 authority is DIAGNOSTIC; promotion needs a new ADR + proof.
7. MCE global commodity stays independent and off unless separately accepted.
8. No thin fake sector maps that invent product coverage without real drivers.

## Non-goals (v1)

- Per-ticker custom macro maps (beyond sector membership)
- News / geopolitics NLP
- Replacing MCE or peer `SectorContextEvidence`
- Decision authority or risk gate changes
- Rates curve / BI7DRR without a clean series contract
- Auto-enabling MCE `commodity_composite`
- Full IDX sector map coverage on day one
- Adding oil (`CL=F`) before series reliability is proven

## Consequences

- **Positive:** analysts and pipelines get an explicit, replayable “watch these
  macros for this sector” object; energy use case is honest and attributable;
  architecture stays aligned with evidence-authority rules.
- **Cost:** new config surface, fingerprint fields, and fetch coverage for
  commodity/FX series when energy analysis runs; dual commodity story
  (global MCE vs routed sector) must stay documented to avoid confusion.
- **Follow-up:** S4 research/attribution hooks; map expansion only with ≥2 real
  drivers; continuous local rates (P2b) separate from BI policy steps;
  promotion ADR only after walk-forward proof. TUI panel parity optional.

## Implementation pointers

| Layer | Artifact |
|-------|----------|
| Domain | `src/domain/value_objects/sector_macro_context_evidence.py` |
| Application | `src/application/services/sector_macro_context_evidence_builder.py` |
| Application | `src/application/services/candidate_sector_macro_context_evidence_assembler.py` |
| Application | `src/application/services/ticker_dashboard_sector_macro_loader.py` (view browse) |
| Infrastructure | `src/infrastructure/config/sector_macro_context_config_loader.py` |
| Config | `config/sector_macro_context.yaml` |
| Fingerprint | `smc_*` on `SignalObservationFingerprint` (observation schema v9) |
| Adapter (panel) | `src/adapters/cli/screen_accum_sector_macro_display.py` — shared builder; used by single-ticker **screen** judgment and **view** full dashboard. `plan_swing_sector_macro_context_display.py` is a re-export only (plan is structure desk; ADR-054). |
| Surfaces | `saham screen accum TICKER` (judgment); `saham view ticker show` full (browse). Universe board skips attach for latency; fingerprints may still build SMC on observation persist. |
| Fetch | Live-map Yahoo series auto-refresh on `saham fetch market` (`sector_macro` labels); macro calendar via ADR-055 (`BI_RATE` policy spine for bank map). |
| Tests | builder/VO/loader + authority firewall + screen/view panel unit tests |

Promotion and additional sector maps remain future work (see Non-goals).
