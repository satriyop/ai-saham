# Retire Accum Group-Breadth Score Bonus

Status: `READY_FOR_IMPLEMENTATION`

Authority: [ADR-062](../../docs/adr/ADR-062-retire-accum-group-breadth-production-bonus.md)

Contract lock commit prerequisite: this file and ADR-062 were amended on
2026-08-02 with closed classification, schema-12 fork, targeted rejection,
inventory, research/ml-saham companions, golden gate, and end-state wiring.
Implementation must not start from an older “dormant-only / no identity fork”
reading of ADR-062.

Prior interim status while locks were open:
`IMPLEMENTATION_BLOCKED_ON_COMPAT_LOCK` (cleared by the documentation lock).

## 1. Task Metadata

- Task title: Remove the retired accumulation group-breadth score bonus
- Task type: Refactor / clean break
- Priority: High
- Primary owner: `ai-saham`
- Mandatory companion owner: `ml-saham` (executable consumers; not optional docs)
- Semantic classification matrix (closed):

| Surface | Classification |
|---|---|
| Live Accum, Signal, Risk, Action and ordering | `NON_SEMANTIC`, proven by offline golden |
| Removed config paths and config-hash inputs | `CONFIG_MATERIAL` |
| Removed candidate payload fields | `OBSERVATION_SCHEMA` |
| Semantic engine version | Unchanged |
| SQLite learning schema | Unchanged |
| Snapshot contract | Remains `production_policy_snapshot.v2`, seven rows |
| Lean contract ID | Remains `lean_accumulation_compatibility.v2` |
| Compatibility value | Must fork |

Required producer version action:

- Bump `ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION` `11` → `12`.
- Alias `CANDIDATE_OBSERVATION_SCHEMA_VERSION` follows.
- Schema-11 rows stay immutable historical corpus; schema-12 starts a new cohort.
- No semantic-engine bump, snapshot v3, lean-v3 contract ID, or SQLite migration.

ADR-062 clarification: “lean v2 unchanged” means the **contract ID** remains
v2, not that the compatibility hash remains equal.

## 2. Chosen Decision

Remove the dormant conglomerate-group breadth score mutation and all
active-looking production-policy surfaces. Implement this option only.

Production currently supplies no group mapping and skips the applier. Live
Accum/Signal/Risk/Action/ordering must remain golden-equivalent. Removing the
four material config fields and the candidate payload fields still forks
`compatibility_id` for new captures. Do not activate, replace, or redesign
breadth in this task.

## 3. Locked Implementation Decisions

### 3.1 Retired YAML rejection — option C (targeted)

- Delete `accumulation_screener.sector_breadth` from shipped
  `config/accumulation_screener.yaml`.
- The accumulation/swing policy composition path must **reject** that exact
  retired section if present in loaded config.
- Direct typed construction with retired keyword arguments must fail naturally.
- Do **not** make every unrelated YAML loader globally strict.
- Do **not** silently ignore private configurations that still contain the
  retired section.

### 3.2 Scope of `idx_groups`

Removal is limited to accumulation breadth scoring.

Keep:

- `config/idx_groups.yaml`
- `GroupMappingService`
- sentiment/group display consumers
- unrelated conglomerate-context behavior

Remove:

- `AccumulationScreenUseCase.idx_groups`
- corresponding factory parameters
- ticker-to-group accumulation mapping
- `AccumulationSectorBreadthApplier`
- all accumulation request/config/fingerprint/payload transport for the bonus

Rewrite of the old global wording:

> Do not inject `idx_groups` into any accumulation screen, capture, backfill,
> cron, briefing, or alternate accumulation-scoring path.

### 3.3 Snapshot exclusion

Keep the explicit exclusion entry; correct wording to:

> Retired from production policy by ADR-062; never part of the production
> accumulation baseline.

Existing snapshot rows remain unchanged. New schema-12 cohorts receive seven
snapshot-v2 rows under their new compatibility ID.

### 3.4 End-state wiring invariant

> No `idx_groups` constructor/factory parameter, no ticker-to-group state, no
> breadth applier type, and no accumulation production composition reference.

Tests must assert **absence**, not that the default remains `None`.

### 3.5 Golden equivalence

Use an offline deterministic synthetic fixture—not a live LQ45 run—as the
reproducibility gate.

Before production code edits, freeze and store under focused test fixtures:

- ordered ticker list;
- candidate inclusion/exclusion;
- Accum score and breakdown;
- Signal raw/exact score and Action;
- Risk result/gates where the workflow produces them;
- setup phase/readiness;
- final serialized projection, excluding nondeterministic timestamps;
- SHA-256 of the frozen fixture payload.

Record fixture path and hash in §11 Completion Record before merge of the
implementation commit. A real dated screen may be supplementary evidence only.

Fixture path/hash (fill before implementation edits):

```text
Path:
SHA-256:
```

### 3.6 Research scope (active consumers)

In scope:

- delete or retire `research/scripts/factor_card_sector_breadth.py`;
- remove active `research/README.md` commands and feeder claims for the bonus;
- remove `sector_breadth_pct` / `sector_breadth_bonus` from
  `research/lab/panel.py`;
- update active `docs/research/engine_factor_inventory_and_ml_proving.md` claims;
- retain old generated research artifacts only as clearly historical,
  non-executable records;
- protect unrelated `sc_sector_breadth` sector-context diagnostic consumers.

### 3.7 ml-saham companion (mandatory)

Executable consumers must be cleaned in a coordinated ml-saham commit after
ai-saham implementation:

- remove candidate-panel aliases for `sector_breadth_bonus` /
  `sector_breadth_pct` that model the retired Accum score bonus
  (see `src/ml_saham/challenge/panel.py` and related extract paths);
- remove static/reference policy remnants that model the `+10` bonus
  (e.g. `accum_score_weights.fixture.v1.json` sector_breadth sleeve notes);
- bump any affected panel/adapter identity required by ml-saham contracts;
- preserve historical artifacts without granting production eligibility;
- protect unrelated sector-context / diagnostic breadth paths
  (`sc_sector_breadth`, diagnostic peer breadth) that are not the retired bonus;
- do not invent a production breadth PolicySpec or baseline.

### 3.8 Commit order

One coordinated work session with scoped commits:

1. **This** ai-saham documentation/contract-lock commit.
2. ai-saham implementation commit (code + tests + golden).
3. ml-saham companion clean-break commit.
4. Cross-repo re-vet against both final commits.
5. Record all hashes in §11 Completion Record.

Existing ADR-062 and roadmap links alone are not sufficient: active research
and ml-saham executable consumers still need removal.

## 4. Required Dependency Order

1. Confirm this contract lock (ADR-062 + this task) is the committed authority.
2. Inventory every producer and consumer (see §5); refresh if tree drifted.
3. Freeze offline golden fixture + SHA-256 before production code edits.
4. Bump observation payload schema 11 → 12 and remove material config-hash
   inputs; accept compatibility fork for new captures.
5. Remove the score mutation and application wiring surface (absence tests).
6. Apply targeted YAML rejection for `accumulation_screener.sector_breadth`.
7. Remove typed config/request and observation-transport remnants in producer
   to consumer order.
8. Clean research active consumers; correct snapshot exclusion prose.
9. Re-run golden equivalence, snapshot closed-set, observation round-trip,
   composition absence, full test, and lint gates.
10. Land ml-saham companion clean-break; re-vet both repos; record hashes.

Stop before editing if implementation would silently reinterpret stored fields,
keep aliases/fallbacks, or claim schema-11 and schema-12 share one cohort.

## 5. Complete Inventory (lock-time, 2026-08-02)

Refresh only if paths move; do not use inventory refresh to reopen identity law.

### 5.1 Remove — accumulation group-breadth score bonus

| Area | Path / symbol |
|---|---|
| Shipped config section | `config/accumulation_screener.yaml` → `sector_breadth` (`enabled`, `breadth_threshold`, `bonus_pts`, `min_tickers_for_breadth`) |
| Applier | `src/application/services/accumulation_sector_breadth.py` → `AccumulationSectorBreadthApplier` |
| Use case seam | `AccumulationScreenUseCase.idx_groups` / ticker-to-group map / apply order |
| Config load | `src/infrastructure/config/swing_policy_config_loader.py` sector_breadth fields |
| Config-hash inputs | `src/domain/value_objects/signal_semantic_contract.py` keys `accumulation_screener.sector_breadth.*` |
| Fingerprint material | `src/application/services/accumulation_observation_fingerprint.py` (`sector_breadth_enabled`, `sector_breadth_threshold`, `sector_breadth_bonus_pts`, …) |
| Request/DTO transport | `SwingPolicyConfig` / `AccumulationScreenRequest` / observation request builder fields for breadth |
| Candidate payload | `sector_breadth_pct`, `sector_breadth_bonus` on candidate serialization |
| Snapshot exclusion prose | ADR-059 / snapshot payload exclusion entry (wording correction only) |
| Schema constant | `ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION` / `CANDIDATE_OBSERVATION_SCHEMA_VERSION` in `signal_artifact_schema.py` (11 → 12) |
| Production wiring tests (upgrade) | `tests/adapters/composition/test_sector_breadth_not_in_production_wiring.py` (assert absence, not `None` default) |
| Applier unit tests | `tests/application/services/test_accumulation_sector_breadth.py` (delete or replace with rejection/absence) |
| Fixture constructors | tests passing `sector_breadth_enabled` / threshold / bonus_pts (hard-filter, observation builder, workflow, …) |

### 5.2 Remove or retire — active research consumers

| Path | Action |
|---|---|
| `research/scripts/factor_card_sector_breadth.py` | Delete or retire (non-executable) |
| `research/README.md` commands/claims for that script | Remove active commands |
| `research/lab/panel.py` fields `sector_breadth_pct` / `sector_breadth_bonus` | Remove |
| `docs/research/engine_factor_inventory_and_ml_proving.md` feeder/A3 claims | Update to retired |
| Generated research factor cards mentioning the bonus | Historical only; non-executable |

### 5.3 Keep — unrelated breadth / group concepts

| Path / concept | Why keep |
|---|---|
| `config/idx_groups.yaml` | Conglomerate map still used outside Accum score |
| `GroupMappingService` / group mapping loader | Non-accumulation consumers |
| Sentiment / group display | Not Accum score mutation |
| `sc_sector_breadth` fingerprint / sector-context evidence | Different DIAG metric |
| `sector_context` peer breadth / ADR-053 lane | Different product concept |
| Regime `sector_breadth` proxy fields | Not Accum bonus transport |
| ml-saham curriculum chapter `sector-breadth` (market participation pedagogy) | Curriculum, not production bonus authority |
| ml-saham diagnostic sector peer context | Not production Accum `+10` bonus |

### 5.4 ml-saham executable companions (mandatory)

| Path | Action |
|---|---|
| `src/ml_saham/challenge/panel.py` aliases mapping `sector_breadth_bonus` / `peer_breadth` / etc. into Accum `sector_breadth` score component | Remove retired bonus extract paths / aliases that model production bonus |
| `src/ml_saham/challenge/policies/accum_score_weights.fixture.v1.json` sleeve for `sector_breadth` / +10 note | Remove or re-version so static reference does not model retired production bonus |
| Factor validity / payload contract tests expecting bonus extract | Update to fail-closed / non-production |
| Historical challenge artifacts mentioning breadth | Keep as historical; never promotion-eligible as production breadth baseline |

## 6. Do Not Interpret This As

- Do not inject `idx_groups` into any accumulation screen, capture, backfill,
  cron, briefing, or alternate accumulation-scoring path.
- Do not delete `config/idx_groups.yaml` or break non-accumulation group consumers.
- Do not replace conglomerate groups with sectors in this task.
- Do not keep aliases, fallback fields, dual serialization, ignored config
  keys, or a no-op applier for compatibility.
- Do not create or reserve snapshot v3, lean compatibility v3, migration 4, or
  an eighth snapshot row.
- Do not rewrite historical observations, snapshots, or labels.
- Do not claim schema-11 and schema-12 share one `compatibility_id`.
- Do not treat “lean v2 unchanged” as “compatibility hash unchanged”.
- Do not turn the removed score rule into diagnostic corpus evidence.
- Do not let ml-saham invent or mirror a policy absent from production.
- Do not use a live LQ45 run as the sole reproducibility gate.
- Do not assert “default is None” instead of absence of the accumulation seam.

## 7. Layer Plan

```text
Layer plan:
- Domain: schema 11→12; remove retired serialized/domain-facing remnants if inventory proves ownership; keep sc_sector_breadth / sector-context distinct
- Application: remove applier, policy/request fields, fingerprints, workflow transport; absence of idx_groups seam
- Infrastructure: remove accumulation YAML section load; targeted reject of retired section; no new I/O; keep idx_groups loader for other consumers
- Adapter: remove obsolete accumulation composition parameters; production roots must not reference breadth applier
- Research: retire active bonus scripts/panel fields/docs claims
- ml-saham (companion commit): remove executable bonus aliases and static +10 remnants; preserve historical artifacts as non-eligible
```

No new dependency, provider, UI, CLI command, database write, or AI behavior.

## 8. End-to-End Invariants

- The same production inputs produce the same Accum, Signal, Risk, Action,
  candidate inclusion, and ordering before and after removal (offline golden).
- Production accumulation composition has no `idx_groups` parameter, mapping
  state, or breadth applier type (absence).
- Snapshot v2 remains exactly seven verified rows and excludes breadth with
  corrected ADR-062 exclusion prose.
- New canonical producers emit schema-12 payloads without retired fields and
  mint a new compatibility cohort. Historical schema-11 rows remain immutable
  raw facts and gain no new authority.
- Lean contract ID remains `lean_accumulation_compatibility.v2`; compatibility
  **values** differ across the schema fork.
- Unrelated sector-context evidence (`sc_sector_breadth`, peer breadth DIAG)
  remains intact.
- ml-saham continues to verify/challenge the real seven-policy baseline only;
  no reconstructed `+10` production bonus.

## 9. Required Tests

- Negative production-composition test: no group map or breadth applier type /
  parameter can appear in screen, capture, backfill, cron, briefing, or
  alternate accumulation roots (**absence**, not `None` default).
- Offline golden production-output equivalence (fixture path/hash recorded).
- Targeted config rejection for `accumulation_screener.sector_breadth`; silent
  ignore forbidden on that composition path.
- Typed construction with retired kwargs fails naturally.
- Observation serialization/read tests: schema-12 without retired payload
  fields; schema-11 historical rows remain readable as historical only.
- Snapshot test: exact seven v2 IDs, no breadth ID, no v3 constants/artifacts;
  exclusion prose present.
- Regression tests protecting `sc_sector_breadth` / sector-context contracts.
- Research active-path smoke: retired script/commands not advertised as live.
- ml-saham companion: no executable bonus aliases; static fixture does not model
  production `+10`; historical packs non-eligible.
- `git diff --check`.
- Focused tests, architecture-boundary tests, and full test suite on ai-saham.
- Whole-repository `ruff check src/ tests/` and
  `ruff format --check src/ tests/` after the final Python edit on ai-saham.
- ml-saham verification per its `AGENT_QUICKSTART.md` matrix for touched paths.

## 10. Close Criteria

- [x] Pre-edit inventory and compatibility decision are recorded in this task
      (contract lock).
- [x] ADR-062 amended for schema-12, lean contract-ID meaning, targeted
      rejection, companions, and golden gate.
- [ ] Offline golden fixture frozen with path + SHA-256 before code edits.
- [ ] Every retired producer/consumer surface is removed in dependency order.
- [ ] No forbidden alias, fallback, no-op transport, or accumulation wiring remains.
- [ ] Production-output equivalence is proven on the offline golden.
- [ ] Snapshot v2 and unrelated sector-context contracts remain green.
- [ ] Research active consumers retired; historical research packs non-executable.
- [ ] ml-saham companion clean-break landed and re-vet recorded.
- [ ] Focused, architecture, full-suite, diff, and Ruff gates pass after final
      ai-saham Python edits.
- [ ] Commit order followed; hashes recorded in §11.

## 11. Completion Record

```text
Contract lock date/commit: 2026-08-02 / docs(adr-062): lock schema-12 compat fork
  for breadth retirement (docs-only; resolve hash via git log --grep=adr-062)
Implementation date/commit (ai-saham):
Companion date/commit (ml-saham):
Cross-repo re-vet date:
Golden fixture path:
Golden fixture SHA-256:
Schema versions: 11 (historical) → 12 (new capture)
Lean contract ID: lean_accumulation_compatibility.v2 (unchanged ID; forked values)
Snapshot contract: production_policy_snapshot.v2 / seven rows
Known limitations: pre-lock partial code edits remain unstaged in the worktree
  and must be rebased against this lock before the implementation commit
```

## 12. Final Readiness Gate

This task is `READY_FOR_IMPLEMENTATION` for **code** only after the
documentation lock is committed and the offline golden fixture is frozen.
Do not start producer code removal while classification, schema-12,
compatibility fork, targeted rejection, inventory, or companion scope are
reopened. Any attempt to keep hash equality, silently ignore retired YAML,
delete global `idx_groups`, or skip ml-saham executable cleanup requires a new
task/ADR amendment rather than silent reinterpretation.
