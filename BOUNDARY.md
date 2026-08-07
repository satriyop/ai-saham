# Boundary — `ai-saham` ↔ `ml-saham`

Sibling contract so the two repos do **not** re-own each other’s jobs.

| Repo | Role |
|------|------|
| **`ai-saham` (this repo)** | Production engine + market ingest + **corpus authority** (observations + path labels) |
| **`ml-saham`** | Offline **challenge lab** + curriculum — **owns accum scoring / policy evaluation** |

Sibling path (maintainer default): `~/dev/ml-saham`  
Full mirror of this contract: [`ml-saham/BOUNDARY.md`](../ml-saham/BOUNDARY.md) (if checked out next to this tree).

---

## One-liners

| Ask | Answer in |
|-----|-----------|
| Capture decisions + path labels (3d/10d/20d)? | **`ai-saham`** — `research accum capture|backfill|labels|status` |
| Score the accum book / stress policies / factors? | **`ml-saham`** — `challenge run` / `challenge factor` / engine |
| Fetch / screen / plan / apply YAML | **`ai-saham` only** |

---

## Decision: drop accum cohort evaluate (ai-saham)

**Status:** Accepted (product) — 2026-07-29  
**Scope:** Accumulation discovery corpus only. **Not** pre-open evaluate; **not** swing/policy evaluation tables used by `policy accum`.

### Why

| Fact | Implication |
|------|-------------|
| ml-saham builds panels + metrics from `learning_observations` + `candles` | Does **not** need `research accum evaluate` or `learning_evaluations` for ACCUM |
| Labels already freeze path outcomes per signal date | Real y for the corpus is **`learning_outcome_labels`**, not a rollup row |
| Current `research accum evaluate` is one global pile of all AVAILABLE primary labels | Not time-bounded; weak research value; duplicates ml-saham’s job poorly |

### What is dropped / not product for accum

| Item | Decision |
|------|----------|
| **`saham research accum evaluate`** | **Dropped as product.** Do not require it in cron, runbooks, or agent checklists. CLI may still exist until removed; treat as **legacy / do not use**. |
| **`saham research accum replay`** (evaluation catalog) | Same — legacy if present; not part of the accum pipeline. |
| **Writing new ACCUM rows to `learning_evaluations`** | **Not required.** Existing rows are inert history; purge optional. |
| **Automating multi-horizon evaluate (3/10/20)** | **No.** Not building time-bounded evaluate in ai-saham for accum. |

### What stays required (accum)

| Item | Owner |
|------|--------|
| Capture / backfill observations | ai-saham |
| Labels `accum_3d` / `accum_10d` / `accum_20d` (cron OK) | ai-saham |
| `status` (per-cohort producer readiness) | ai-saham |
| Policy / factor evaluation (IC, folds, WIN·LOSE) | **ml-saham only** |

### Pre-open (unchanged by this decision)

`saham research pre-open evaluate` remains a separate short-horizon lifecycle (cron may keep it). Do not conflate with accum.

---

## Ownership matrix

| Concern | ai-saham | ml-saham |
|---------|:--------:|:--------:|
| Market / broker / IEV fetch & cache | **write** | read |
| Live screen / signal / risk / plan / TUI | **owns** | — |
| `learning_observations` capture / backfill | **write** | **read** (features) |
| `learning_outcome_labels` (`price_path.accum_*`, …) | **SSOT write** | optional join only; not default challenge y |
| `learning_policy_snapshots` (active: `production_policy_snapshot.v4`) | **SSOT write** (typed production policy) | **read-only** digest/contract verify; no invent/repair/backfill |
| Accum **cohort evaluate** / ACCUM `learning_evaluations` | **dropped (legacy)** | **do not depend on** |
| Policy tournament WIN / LOSE / rank IC / folds | — | **owns** |
| Factor KEEP / DEMOTE / DROP_CANDIDATE | — | **owns** |
| Challenge `ChallengePolicyAdapter` (panel/aliases/scorer) | — | **owns** (must not claim to be production policy) |
| Curriculum explore / demo | light / optional | **primary onboarding** |
| Decision memos for tuning | may link | **`docs/decisions/`** |
| Auto-promote config into production | **never from ML; human `--yes` policy path only** | **never** |
| Import the other repo’s Python packages | **no** | **no** |
| Scrapers / Stockbit auth | **owns** | **forbidden** |

---

## Shared SQLite

- Default DB: `data/db/data.db` (this repo).
- `ml-saham` opens it **read-only** (`ML_SAHAM_DB` / `--db`).
- **Only `ai-saham` migrates and writes** `learning_*` and market tables.
- `ml-saham` may write **its own** artifacts under `ml-saham/artifacts/` (or optional learning store) — never into this DB’s learning tables.

### ADR-056 corpus (accum)

| Artifact | Owner | Notes |
|----------|--------|--------|
| 1 obs / ticker-session, features 7/30/90 | ai-saham write | `learning_observation.accumulation_discovery.v2` |
| Labels 3d / **10d primary** / 20d | ai-saham write | SUCCESS / FAILURE / NEUTRAL; entry = `shared.current_price`; 10d = next 10 sessions **per signal date** |
| Policy snapshots (ADR-059) | ai-saham write | Active: nine closed `production_policy_snapshot.v4` rows per behavioral `compatibility_id` before observation writes, including the unevaluable-gate and resolved signal decision policies. Historical v1-v3 sets remain immutable and ineligible. `ml-saham` verifies digests with no fallback |
| Cohort evaluate | **dropped** | Scoring → ml-saham challenge |
| Challenge panel | ml-saham | Features from observations; protocol y from candles (excess vs IHSG) by default |

### ADR-059 production policy snapshots

- **Writer:** `ai-saham` only, from the same resolved typed policies used by live
  engines / default screen hard-filter policy (`AccumulationProductionPolicyBundle`
  including `hard_filter_policy`).
- **Active contract:** `production_policy_snapshot.v4` — exactly nine rows per
  cohort (the immutable v3 eight plus `signal.accum.decision_policy`).
- **Historical:** `production_policy_snapshot.v1`/v2/v3 closed sets remain
  readable and immutable; none is eligible for current production challenges.
- **Behavioral binding:** ADR-068 compatibility folds behavioral probe digest,
  active snapshot-set payload digest, and observation payload schema version.
- **Reader:** `ml-saham` opens SQLite read-only; recomputes `payload_digest` with the
  shared canonical JSON rules; returns `BLOCKED_POLICY` on missing/mismatch; active
  eligibility requires v4/nine with no historical fallback.
- **Not production authority:** packaged `ml-saham` policy JSON after cutover
  (fixtures/challengers only).
- **Not in snapshot:** ML `panel_kind`, extraction aliases, folds, metrics,
  diagnostic bags.
- Historical cohorts without the active snapshot set are ineligible for verified
  `baseline=production`.

### ADR-068 behavioural cohort identity (ACCUM only)

- **Identity material** for `ACCUMULATION_DISCOVERY` is exactly three parts:
  behavioural probe digest + ADR-059 snapshot payload digest + observation
  payload schema version. Nothing else.
- **Deleted proxies:** raw config-file hashing, `SEMANTIC_ENGINE_VERSION`, and
  `EVIDENCE_CONTRACT_VERSION` are gone for accum identity. Do not reintroduce
  hand-typed engine version bumps as the cohort key.
- **Probe coverage is a measured floor, not a proof of behavioural
  equivalence.** CI enforces branch coverage and a mutation suite over the
  accum decision path. A change that only hits unprobed branches can still
  fail to fork; that gap is named, not denied.
- **`producer_source_revision`** is recorded on every observation as
  **provenance beside identity** (also still on population bindings and
  policy snapshots). It must not enter `observation_id` or `artifact_digest`.
  Multi-build cohorts under one `compatibility_id` are expected and reassuring.
- **Pre-open identity is unchanged** by ADR-068 (purpose isolation).
- **ml-saham** continues to key panels on opaque `compatibility_id` values; it
  does not recompute the probe digest. Treat a new id as a new cohort forever.

Horizons **3 / 10 / 20** (primary **10**) align by number.  
**Label math is not the same product** as challenge excess (see vocabulary).

---

## Vocabulary (do not conflate)

| Term | Means in **ai-saham** | Means in **ml-saham** |
|------|----------------------|----------------------|
| **label** | Row in `learning_outcome_labels` | Protocol panel target (often continuous excess) |
| **evaluate (accum)** | **Dropped** — do not use as book authority | Prefer **`challenge run`** |
| **evaluate (pre-open)** | Still valid short-horizon cohort tool | N/A unless a pre-open challenge protocol |
| **WIN / LOSE** | N/A for research accum | Challenge verdict only |
| **primary 10d** | `price_path.accum_10d.v1` path label contract | Protocol primary H=10 for IC |

---

## What this repo must **not** grow into

- No production-vs-challenger **policy tournament** on research CLI  
- No rank-IC fold engine as default research authority  
- No factor KEEP/DEMOTE product surface  
- No **revival** of accum cohort evaluate “to feed ml-saham” (ml-saham does not consume it)  
- No silent rewrite of corpus labels from challenge artifacts  

**Policy stress tests and promotion decision support** live in `ml-saham`.

---

## Operator flows

```text
# Corpus (this repo) — required
saham research accum backfill|capture
saham research accum labels --all-label-contracts
saham research accum status   # per-cohort LEGACY_RAW_ONLY|BLOCKED_POLICY|COLLECTING|CHALLENGE_INPUT_READY
# Nightly (after EOD refresh): scripts/cron_accum_challenge_corpus.sh
#   capture --universe lq45 → labels --all-label-contracts → status (fail-closed)

# Do NOT rely on:
# saham research accum evaluate
# saham research accum replay

# Policy / book scoring (sibling)
cd ~/dev/ml-saham
export ML_SAHAM_DB=~/dev/ai-saham/data/db/data.db
ml-saham doctor --deep
ml-saham challenge run screener.accum.score_weights --against equal_sleeves
# Human may later change ai-saham config — never auto
```

---

## Doc pointers

| Need | Where |
|------|--------|
| This boundary (ai-saham) | [BOUNDARY.md](./BOUNDARY.md) |
| Sibling boundary | `ml-saham/BOUNDARY.md` |
| Accum observation/label contracts | [docs/adr/ADR-056-…](./docs/adr/ADR-056-accum-corpus-session-observation-and-accum-path-labels.md) |
| Learning pipeline (historical evaluate language) | [docs/adr/ADR-049-…](./docs/adr/ADR-049-database-owned-learning-pipeline-clean-break.md) — **accum evaluate product superseded by this BOUNDARY** |
| Challenge product (sibling) | `ml-saham/docs/challenge_product.md`, ADR-001/002 there |

When this file and informal chat disagree, **this file + ADRs win** (this BOUNDARY wins over older “must evaluate cohort” copy for **accum**).
