# Architecture Decisions

This file is the compact routing hub for binding architectural decisions. Read
the current snapshot and task matrix first, then open only the ADRs relevant to
the task. Individual decisions live under [`docs/adr/`](docs/adr/).

## Authority and reading rules

When sources disagree:

1. Current executable code and tests describe implemented behavior.
2. Accepted ADRs describe architectural intent; a newer amendment wins.
3. Shipped config describes current policy and thresholds.
4. Guides, examples, archived rationale, and plans may lag implementation.

An ADR marked **implementation evolved** states only the surviving contract and
a short migration note. Retired commands, schemas, and implementation proposals
belong in git history, not the default agent reading path. Verify exact current
mechanics in source and live `saham --help`.

Agents should not read all ADRs by default. Use the task matrix below and follow
amendment links from the selected ADRs.

## Current architecture snapshot

_Content recertified against source/config/tests: 2026-07-26. Verify source when making code claims._

```text
providers / SQLite
        -> application evidence builders
        -> SignalEngine + MarketContextEngine
        -> RiskEngine
        -> AssessTradeSetupUseCase
        -> CLI response

canonical observations
        -> forward labels
        -> replay / evaluation / readiness
        -> validator-gated tuning and promotion
```

| Concern | Current implementation |
|---|---|
| Core posture | Deterministic-first, local-first, rule-first; AI is optional and non-authoritative |
| Model use | The deterministic engine remains independently executable; validated narrow local-ML outputs may become governed evidence, while full ML/API decisions remain parallel non-authoritative challengers |
| Layers | Pure domain; application-owned workflow/policy; infrastructure-owned I/O; thin adapters; executable boundary tests |
| Dependency injection | Explicit manual DI; concrete composition belongs in infrastructure composition roots or thin CLI factories |
| Signal | `SignalEngine` delegates canonical scoring to `AssessSignalEvidenceUseCase`; current signal semantics are being repaired through the signal-evidence program |
| Risk | `RiskEngine` owns deterministic structural/execution gates and emits OPEN/BLOCKED assessments |
| Market context | `MarketContextEngine` is a canonical signal-conditioning input when requested; regime-adjusted risk remains a preview |
| Final action | `AssessTradeSetupUseCase` is the single Signal + Risk composition point |
| Screen adoption | `ScreenAssessmentPipeline` + per-scenario seam (`SignalInputs` / `RiskInputsBuilder` / `ScreenPolicy`); engines stay single (ADR-047) |
| Pre-open signal | `pre_open_directional_baseline.v1`: IEP/book agreement sets direction, locked-input IEV sets confidence, auction quality caps action; one `SignalEngine`; TradeSetup owns action; v3 DB observations retain factors and rationale (ADR-048) |
| Evidence promotion | Diagnostic evidence cannot gain production authority without out-of-sample proof and validator support |
| Persistence | Local SQLite at `data/db/data.db`, plus purpose-specific journals/artifacts; historical claims require point-in-time provenance |
| CLI authority | `src/adapters/cli/main.py` and live `saham --help`; adapters wire and render but do not own policy |

## Task-to-ADR reading matrix

Read the smallest applicable set. Cross-cutting tasks may require more than one
row.

| Task area | Required decisions |
|---|---|
| Architecture, layers, DI, composition | [003](docs/adr/ADR-003-hexagonal-ports-adapters-architecture.md), [004](docs/adr/ADR-004-pure-domain-layer.md), [021](docs/adr/ADR-021-strict-boundary-enforcement-infrastructure-decoupling-hexagonal-audit-clean-up.md), [033](docs/adr/ADR-033-workflow-composition-artifact-boundaries.md), [040](docs/adr/ADR-040-manual-dependency-injection-and-composition-roots.md) |
| Signal scoring and evidence authority | [024](docs/adr/ADR-024-signal-engine-and-risk-engine-as-first-class-application-services.md), [025](docs/adr/ADR-025-signalengine-architecture.md), [030](docs/adr/ADR-030-accumulation-screener-evidence-split.md), [037](docs/adr/ADR-037-marketcontext-promotes-from-preview-only-to-canonical-signal-input.md), [039](docs/adr/ADR-039-foreign-flow-score-rescale-to-0-100-amends-adr-030.md), [041](docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md), [043](docs/adr/ADR-043-score-naming-vocabulary.md), [047](docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md), [057](docs/adr/ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md), [062](docs/adr/ADR-062-retire-accum-group-breadth-production-bonus.md) |
| Risk and final trade action | [010](docs/adr/ADR-010-risk-gates-as-policy-layer.md), [022](docs/adr/ADR-022-idx-regular-market-price-floor-rp-50-enforcements.md), [024](docs/adr/ADR-024-signal-engine-and-risk-engine-as-first-class-application-services.md), [026](docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md), [028](docs/adr/ADR-028-idx-market-microstructure-rules.md), [031](docs/adr/ADR-031-swing-setup-evaluation-boundary.md), [032](docs/adr/ADR-032-analyze-swing-verdict-boundary.md), [047](docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md), [054](docs/adr/ADR-054-screen-judge-plan-structure-contract.md) |
| Market context | [029](docs/adr/ADR-029-market-context-engine-mce-third-first-class-application-service.md), [037](docs/adr/ADR-037-marketcontext-promotes-from-preview-only-to-canonical-signal-input.md), [047](docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md) |
| Sector context / sector macro drivers | [053](docs/adr/ADR-053-sector-macro-context-evidence.md), [029](docs/adr/ADR-029-market-context-engine-mce-third-first-class-application-service.md), [041](docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md), [009](docs/adr/ADR-009-config-driven-behavior.md) |
| Screen scenario engine adoption | [047](docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md), [024](docs/adr/ADR-024-signal-engine-and-risk-engine-as-first-class-application-services.md), [026](docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md), [029](docs/adr/ADR-029-market-context-engine-mce-third-first-class-application-service.md), [041](docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md) |
| Pre-open signal evidence, open observations, capture at NCP | [048](docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md), [047](docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md), [041](docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md), [026](docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md), [027](docs/adr/ADR-027-risk-signal-learning-loop.md) |
| Data providers, persistence, PIT/replay | [005](docs/adr/ADR-005-local-first-persistence.md), [006](docs/adr/ADR-006-market-data-provider-abstraction.md), [008](docs/adr/ADR-008-decoupled-fetch-vs-analyze-data.md), [019](docs/adr/ADR-019-unified-fetch-timestamp-fetched-at-datetime-on-cached-domain-value-objects.md), [034](docs/adr/ADR-034-date-field-semantics.md), [036](docs/adr/ADR-036-persisted-jwt-token-store-replaces-playwright-per-invocation-for-stockbit-data-fetching.md), [038](docs/adr/ADR-038-point-in-time-enrichment-and-conservative-derived-fundamentals.md) |
| Indicators, strategies, plugins | [007](docs/adr/ADR-007-indicator-initialization-warm-up-policy.md), [009](docs/adr/ADR-009-config-driven-behavior.md), [012](docs/adr/ADR-012-oss-encapsulation-rule.md), [016](docs/adr/ADR-016-formula-dsl-domain-specific-language-for-indicators.md), [017](docs/adr/ADR-017-plugin-based-indicator-registration.md) |
| CLI and file organization | [011](docs/adr/ADR-011-offline-capable-cli-as-primary-interface.md), [018](docs/adr/ADR-018-cli-command-depth-saham-view-broker-exception.md), [020](docs/adr/ADR-020-cli-adapter-file-naming-convention.md), [023](docs/adr/ADR-023-codebase-directory-and-use-case-file-naming-standards.md), [044](docs/adr/ADR-044-view-subject-taxonomy-ticker-vs-desk.md), [045](docs/adr/ADR-045-view-browse-parity-cli-tui-json-table.md), [046](docs/adr/ADR-046-cli-response-envelope.md), [050](docs/adr/ADR-050-cli-verb-contracts.md), [054](docs/adr/ADR-054-screen-judge-plan-structure-contract.md) |
| CLI verb contracts (plan / inspect / assess) | [050](docs/adr/ADR-050-cli-verb-contracts.md), [054](docs/adr/ADR-054-screen-judge-plan-structure-contract.md), [020](docs/adr/ADR-020-cli-adapter-file-naming-convention.md), [032](docs/adr/ADR-032-analyze-swing-verdict-boundary.md), [033](docs/adr/ADR-033-workflow-composition-artifact-boundaries.md), [049](docs/adr/ADR-049-database-owned-learning-pipeline-clean-break.md) |
| Screen judgment vs plan trade structure | [054](docs/adr/ADR-054-screen-judge-plan-structure-contract.md), [050](docs/adr/ADR-050-cli-verb-contracts.md), [032](docs/adr/ADR-032-analyze-swing-verdict-boundary.md), [033](docs/adr/ADR-033-workflow-composition-artifact-boundaries.md), [031](docs/adr/ADR-031-swing-setup-evaluation-boundary.md), [057](docs/adr/ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md) |
| View browse (stock vs desk, JSON/table, TUI parity) | [044](docs/adr/ADR-044-view-subject-taxonomy-ticker-vs-desk.md), [045](docs/adr/ADR-045-view-browse-parity-cli-tui-json-table.md), [046](docs/adr/ADR-046-cli-response-envelope.md), [018](docs/adr/ADR-018-cli-command-depth-saham-view-broker-exception.md) |
| CLI/TUI machine JSON and response envelope | [046](docs/adr/ADR-046-cli-response-envelope.md), [045](docs/adr/ADR-045-view-browse-parity-cli-tui-json-table.md), [011](docs/adr/ADR-011-offline-capable-cli-as-primary-interface.md), [040](docs/adr/ADR-040-manual-dependency-injection-and-composition-roots.md) |
| Screen discovery JSON / watchlist export | [046](docs/adr/ADR-046-cli-response-envelope.md), [030](docs/adr/ADR-030-accumulation-screener-evidence-split.md), [043](docs/adr/ADR-043-score-naming-vocabulary.md), [040](docs/adr/ADR-040-manual-dependency-injection-and-composition-roots.md) |
| AI and sentiment | [002](docs/adr/ADR-002-rule-first-ai-optional-design.md), [013](docs/adr/ADR-013-ai-agent-governance.md), [014](docs/adr/ADR-014-full-ai-mode-explicit-bypass-mode-rejected.md), [015](docs/adr/ADR-015-sentiment-analysis-classification.md), [042](docs/adr/ADR-042-deterministic-champion-and-optional-model-challengers.md), [060](docs/adr/ADR-060-read-only-tui-context-agent.md), [061](docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) |
| TUI cockpit and optional context agent | [051](docs/adr/ADR-051-tui-opencode-cockpit-clean-break.md), [060](docs/adr/ADR-060-read-only-tui-context-agent.md), [061](docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md), [040](docs/adr/ADR-040-manual-dependency-injection-and-composition-roots.md), [042](docs/adr/ADR-042-deterministic-champion-and-optional-model-challengers.md) |
| Learning, tuning, evaluation, ML preparation | [049](docs/adr/ADR-049-database-owned-learning-pipeline-clean-break.md), [056](docs/adr/ADR-056-accum-corpus-session-observation-and-accum-path-labels.md), [027](docs/adr/ADR-027-risk-signal-learning-loop.md), [033](docs/adr/ADR-033-workflow-composition-artifact-boundaries.md), [038](docs/adr/ADR-038-point-in-time-enrichment-and-conservative-derived-fundamentals.md), [041](docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md), [042](docs/adr/ADR-042-deterministic-champion-and-optional-model-challengers.md), [048](docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md), [057](docs/adr/ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md) |

## Amendment and migration map

| Older decision | Read together with | Effective rule |
|---|---|---|
| ADR-002 T2 AI tuner plan | ADR-027 and current tuning source | Tuning proposals are non-authoritative; the current workflow is deterministic and validator-gated |
| ADR-010 risk profiles | ADR-024 and current `RiskEngine` | OPEN/BLOCKED gate pipeline; no conservative/balanced/aggressive runtime modes |
| ADR-024/025 six-factor signal | Current ADR-024/025 contracts | Staged evidence is canonical; retired scorer details are available in git history |
| ADR-027 proposed `swing learn ...` CLI | Current source and live help | Use the current trade backtest/tune/review/patch/status commands |
| ADR-030 0–120 foreign-flow scale | ADR-039 | Foreign-flow score and matching thresholds use 0–100 |
| ADR-039 `foreign_flow_score` label | ADR-043 | Accumulation composite is `accum_score`; profile participation metric keeps `foreign_flow_score` |
| ADR-018 `view broker` depth + old ticker-centric verbs | ADR-044, ADR-045 | Three-level `view ticker` and `view broker` allowed; stock deep-dives under ticker; desk under broker CODE; table/json + use-case parity in 045 |
| ADR-045 view-only JSON envelope | ADR-046 | Envelope top-level keys are CLI-wide; view keeps ticker/desk specialization and browse parity; other families adopt clean-break on touch |
| ADR-032 MCE preview-only signal | ADR-037 | MCE can condition canonical signal; risk adjustment remains preview |
| DQ-002J post-score availability attachment | ADR-041 | Temporary shadow prototype; the target is a shared pre-score evidence/provenance/availability boundary |
| ADR-002/014 optional AI and rejected bypass | ADR-042 | Narrow validated local-ML evidence may enter the governed evidence lifecycle; full ML/API decision challengers remain separate shadow outputs |
| ADR-023 file-owned learning paths | ADR-049 | SQLite owns all learning artifacts; opening tracks and swing patch/review files are retired without migration |
| ADR-032/033 `analyze swing` / overloaded `analyze` family | ADR-050 | Target verbs: `plan swing` (TradeSetup), `inspect *` (lenses), `assess pre-open` (frozen confirm); `analyze` top-level retired on implementation |
| ADR-050 `plan` as full analysis desk / `screen` discovery-only | ADR-054 | `screen` = judge candidates (universe + single-ticker deep); `plan` = trade structure (horizon/SL/TP); phased migration |
| ADR-051 AI chat non-goal | ADR-060 and ADR-061 | The cockpit may host one optional context assistant; Phase 1 is zero-tool, while a separately gated closed read-tool subset is allowed; general chat, writes, CLI passthrough, open-ended tools, and AI decision authority remain excluded |
| ADR-059 sector-breadth exclusion | ADR-062 | The dormant conglomerate-group breadth bonus is retired from production policy; snapshot v2 remains exact (seven rows); lean **contract ID** stays `lean_accumulation_compatibility.v2` while observation schema 11→12 **forks compatibility values**; any future diagnostic is a new PIT-governed evidence contract rather than activation of the old rule |

## High-value implementation entry points

| Decision area | Current source |
|---|---|
| CLI surface | `src/adapters/cli/main.py` |
| CLI response envelope (view) | `src/application/dto/view_ticker_contract.py` |
| CLI response envelope (screen) | `src/application/dto/screen_contract.py` |
| Engine construction | `src/application/services/engine_bootstrap/` |
| Signal facade and scorer | `src/application/services/signal_engine.py`, `src/application/use_case/assess_signal_evidence_use_case.py` |
| Risk facade | `src/application/services/risk_engine.py` |
| Trade setup composition | `src/application/use_case/assess_trade_setup_use_case.py` |
| Screen assessment adoption seam | `src/application/services/screen_assessment_pipeline.py` |
| Pre-open learning loop (current files) | `src/application/use_case/opening_grade_use_case.py`, `research pre-open capture + research pre-open track/grade` CLI |
| Market context | `src/application/services/market_context_engine.py`
| Swing tuning guardrails | `src/application/services/swing_tuning_patch_validation.py` and adjacent `swing_tuning_*` services |
| Layer enforcement | `tests/architecture/test_layer_boundaries.py` |
| Signal-evidence parked residuals | `tasks/backlog/parked_*.md` |
| Signal-evidence archive | `tasks/done/signal_evidence_program.md` |

## Decision index

| ADR | Decision | Current reading |
|---|---|---|
| [001](docs/adr/ADR-001-deterministic-first-core.md) | Deterministic-first core | Accepted |
| [002](docs/adr/ADR-002-rule-first-ai-optional-design.md) | Rule-first, AI-optional | Accepted; T2 implementation evolved |
| [003](docs/adr/ADR-003-hexagonal-ports-adapters-architecture.md) | Hexagonal architecture | Accepted |
| [004](docs/adr/ADR-004-pure-domain-layer.md) | Pure domain | Accepted |
| [005](docs/adr/ADR-005-local-first-persistence.md) | Local-first persistence | Accepted |
| [006](docs/adr/ADR-006-market-data-provider-abstraction.md) | Provider abstraction | Accepted |
| [007](docs/adr/ADR-007-indicator-initialization-warm-up-policy.md) | Indicator initialization | Accepted |
| [008](docs/adr/ADR-008-decoupled-fetch-vs-analyze-data.md) | Fetch/analyze separation | Accepted |
| [009](docs/adr/ADR-009-config-driven-behavior.md) | Config-driven behavior | Accepted |
| [010](docs/adr/ADR-010-risk-gates-as-policy-layer.md) | Risk gates | Accepted; profiles retired |
| [011](docs/adr/ADR-011-offline-capable-cli-as-primary-interface.md) | Offline-capable CLI | Accepted |
| [012](docs/adr/ADR-012-oss-encapsulation-rule.md) | OSS encapsulation | Accepted |
| [013](docs/adr/ADR-013-ai-agent-governance.md) | Agent governance | Accepted |
| [014](docs/adr/ADR-014-full-ai-mode-explicit-bypass-mode-rejected.md) | Full-AI bypass | Rejected |
| [015](docs/adr/ADR-015-sentiment-analysis-classification.md) | Sentiment classification | Accepted |
| [016](docs/adr/ADR-016-formula-dsl-domain-specific-language-for-indicators.md) | Formula DSL | Accepted |
| [017](docs/adr/ADR-017-plugin-based-indicator-registration.md) | Indicator plugins | Accepted |
| [018](docs/adr/ADR-018-cli-command-depth-saham-view-broker-exception.md) | CLI depth exception (`view` sub-groups) | Accepted; amended by ADR-044 |

| [019](docs/adr/ADR-019-unified-fetch-timestamp-fetched-at-datetime-on-cached-domain-value-objects.md) | Fetch timestamp | Accepted |
| [020](docs/adr/ADR-020-cli-adapter-file-naming-convention.md) | CLI adapter naming (`{top}_{sub}_*`) | Accepted; examples refreshed for trade/research/policy tree |
| [021](docs/adr/ADR-021-strict-boundary-enforcement-infrastructure-decoupling-hexagonal-audit-clean-up.md) | Boundary enforcement | Accepted |
| [022](docs/adr/ADR-022-idx-regular-market-price-floor-rp-50-enforcements.md) | IDX Rp50 floor | Accepted |
| [023](docs/adr/ADR-023-codebase-directory-and-use-case-file-naming-standards.md) | Layout and naming | Superseded by ADR-049 |
| [024](docs/adr/ADR-024-signal-engine-and-risk-engine-as-first-class-application-services.md) | First-class Signal/Risk engines | Accepted; Signal implementation evolved |
| [025](docs/adr/ADR-025-signalengine-architecture.md) | SignalEngine architecture | Accepted; canonical scorer evolved |
| [026](docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md) | Signal/Risk composition | Accepted |
| [027](docs/adr/ADR-027-risk-signal-learning-loop.md) | Learning loop | Accepted intent; implementation evolved |
| [028](docs/adr/ADR-028-idx-market-microstructure-rules.md) | IDX microstructure | Accepted; implemented scope clarified |
| [029](docs/adr/ADR-029-market-context-engine-mce-third-first-class-application-service.md) | MarketContextEngine | Accepted |
| [030](docs/adr/ADR-030-accumulation-screener-evidence-split.md) | Accumulation evidence split | Accepted; score scale amended by ADR-039 |
| [031](docs/adr/ADR-031-swing-setup-evaluation-boundary.md) | Swing setup evaluation | Accepted |
| [032](docs/adr/ADR-032-analyze-swing-verdict-boundary.md) | Swing verdict boundary | Accepted; signal rule amended by ADR-037 |
| [033](docs/adr/ADR-033-workflow-composition-artifact-boundaries.md) | Workflow artifact boundaries | Accepted |
| [034](docs/adr/ADR-034-date-field-semantics.md) | Date semantics | Accepted |
| [035](docs/adr/ADR-035-port-method-naming-convention.md) | Port naming | Accepted |
| [036](docs/adr/ADR-036-persisted-jwt-token-store-replaces-playwright-per-invocation-for-stockbit-data-fetching.md) | Stockbit token store | Accepted |
| [037](docs/adr/ADR-037-marketcontext-promotes-from-preview-only-to-canonical-signal-input.md) | MCE canonical signal conditioning | Accepted; amends ADR-032 |
| [038](docs/adr/ADR-038-point-in-time-enrichment-and-conservative-derived-fundamentals.md) | Point-in-time enrichment | Accepted |
| [039](docs/adr/ADR-039-foreign-flow-score-rescale-to-0-100-amends-adr-030.md) | Foreign-flow 0–100 scale | Accepted; amends ADR-030 |
| [040](docs/adr/ADR-040-manual-dependency-injection-and-composition-roots.md) | Manual dependency injection | Accepted |
| [041](docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md) | Canonical signal-evidence input | Accepted; amended 2026-07-22 (discovery ATTACHED_REQUIRED + settled bandar) |
| [042](docs/adr/ADR-042-deterministic-champion-and-optional-model-challengers.md) | Deterministic champion, governed ML evidence, and optional decision challengers | Accepted |
| [043](docs/adr/ADR-043-score-naming-vocabulary.md) | Score naming vocabulary | Accepted |
| [044](docs/adr/ADR-044-view-subject-taxonomy-ticker-vs-desk.md) | View subject taxonomy (ticker vs desk) | Accepted; amends ADR-018 |
| [045](docs/adr/ADR-045-view-browse-parity-cli-tui-json-table.md) | View browse parity (CLI/TUI, table/json) | Accepted; depends on ADR-044; envelope keys generalized by ADR-046 |
| [046](docs/adr/ADR-046-cli-response-envelope.md) | Shared CLI response envelope | Accepted; generalizes envelope beyond view; adopt-on-touch for other families |
| [047](docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md) | Scenario-adoption seam for Signal / Risk / MCE | Accepted; engines single; pre-open directional-baseline amendment mandates removal of its remaining local scorer |
| [048](docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md) | Pre-open signal evidence + observation identity | Accepted; v3 is the unused first cohort and `pre_open_directional_baseline.v1` is its deterministic long-only champion |
| [049](docs/adr/ADR-049-database-owned-learning-pipeline-clean-break.md) | Database-owned learning pipeline clean break | Accepted; supersedes ADR-023 learning persistence; amends ADR-027/033/041/042/048; public CLI family tree (trade/research/policy) |
| [056](docs/adr/ADR-056-accum-corpus-session-observation-and-accum-path-labels.md) | Accum corpus session observation + accum_* path labels | Accepted; amends ADR-049 unit of analysis and label names; primary y = accum_10d |
| [050](docs/adr/ADR-050-cli-verb-contracts.md) | CLI verb contracts (`plan` / `inspect` / `assess`) | Accepted; implementation landed; amends 020/032/033/049; **product roles amended by ADR-054** |
| [051](docs/adr/ADR-051-tui-opencode-cockpit-clean-break.md) | TUI OpenCode daily cockpit clean break | Accepted; Phases 0–5 implemented; supersedes multi-route research TUI UX |
| [052](docs/adr/ADR-052-today-live-first-adapter.md) | `saham today` live-first adapter with offline fallback | Accepted; implementation in progress; scopes ADR-011 (offline-first = engine/domain; `today` = live adapter) |
| [053](docs/adr/ADR-053-sector-macro-context-evidence.md) | Sector macro context evidence (routed per-sector drivers) | Accepted; multi-map + bank BI steps shipped (DIAGNOSTIC, schema v9); panel on screen/view; S4 attribution open |
| [054](docs/adr/ADR-054-screen-judge-plan-structure-contract.md) | Screen judges candidates; plan designs trade structure | Accepted; contract + phased migration S0–S5; amends 032/033/050; policy A + structure-only plan CLI |
| [055](docs/adr/ADR-055-macro-calendar-fetch.md) | Macro economic calendar fetch | Accepted |
| [057](docs/adr/ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md) | Evidence vs diagnostic evidence vs corpus vocabulary | Accepted; operator/agent language; amends overloaded “evidence” usage |
| [058](docs/adr/ADR-058-setup-phase-ledger-production-memory.md) | Setup phase ledger production memory | Accepted |
| [059](docs/adr/ADR-059-production-policy-snapshot-for-ml-challenges.md) | Production policy snapshots for ML challenges | Accepted; active v2 snapshot contract |
| [060](docs/adr/ADR-060-read-only-tui-context-agent.md) | Optional read-only TUI context agent | Accepted; amends ADR-051 for bounded accumulation-Judge explanation |
| [061](docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | Closed read-tool orchestration for the context agent | Accepted architecture; amends ADR-060; runtime activation remains gated |
| [062](docs/adr/ADR-062-retire-accum-group-breadth-production-bonus.md) | Retire accumulation group-breadth production bonus | Accepted; live scoring NON_SEMANTIC (golden); CONFIG_MATERIAL + OBSERVATION_SCHEMA clean-break; schema 11→12 forks compatibility; lean contract ID remains v2; targeted YAML reject; research + ml-saham companions mandatory |

## Adding or changing a decision

- Add one `docs/adr/ADR-NNN-short-name.md` file using: Status, Date, Context,
  Decision, Invariants/Consequences, Non-goals, and implementation pointers as
  applicable.
- Add it to this index and the smallest relevant task-matrix row.
- Record amendments in both affected ADRs and in the amendment map above.
- Preserve amendment relationships and the reason for a change, but keep retired
  implementation inventories in git history rather than active ADR bodies.
- Keep implementation task history, test counts, and file-by-file migration
  inventories in `tasks/`, implementation notes, or archives rather than here.
