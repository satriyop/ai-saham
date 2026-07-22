# DQ-005 Slice B — lean local recompute + drift classification

**Status: DONE** (2026-07-22). Implemented
`VerifyStoredSignalObservationUseCase` + `signal-replay --verify`. Selection
reuses Slice A (never `get_latest`). Cohort mismatch / non-canonical →
`UNREPRODUCIBLE` without screening. Local cutoff-aware re-screen compares
score, signal_authority_coverage, setup_phase, fingerprint_digest →
`MATCH`/`DRIFT`. Residual post-capture backfill risk documented on notes.
No new migrations; no network refetch; no snapshot warehouse.

Companion to `tasks/backlog/audit_data_quality.md` → DQ-005.  
Slice A (retrieval honesty) is **DONE** (`68759bb`, 2026-07-22):
`RetrieveStoredSignalObservationUseCase` is explicitly `RETRIEVAL_ONLY`, names
identity, and returns `AMBIGUOUS` instead of silent `get_latest`.

Slice B adds a **separate** verify path: local cutoff-aware recompute with a
small machine-readable diff. It does **not** replace retrieval.

## Guiding decision

Implement this option only.

> Same ticker/date/identity → re-run the accumulation screen against **local**
> SQLite repos, truncated to the observation’s recorded cutoff / session, with
> a **matching** config cohort → compare a small field set → report
> `MATCH` / `DRIFT` / `UNREPRODUCIBLE`.

**Why this shape (codebase-grounded):**

- Real recompute is useful even without ML (regression / engine honesty).
- Payloads store **outputs**, not frozen input packs — full bit-identical
  provenance (source snapshot IDs, git pin, config blob store) is parked.
- Exchange history rarely rewrites; **local backfill after capture**, **code/
  config drift**, and **cutoff misuse** are the real divergence sources.
- Internet refetch is the wrong move for a local-first product.

**Accepted residual risk (document, do not “fix” with a warehouse):** if
candles/broker/enrichment rows inside the original window were filled or
corrected in SQLite *after* capture, local recompute can drift even when the
exchange did not restate. Call that out in the response notes; do not claim
promotion-grade bit identity.

---

## What already exists (reuse, do not reinvent)

| Piece | Location |
|---|---|
| Retrieval + identity selection | `retrieve_stored_signal_observation_use_case.py` |
| Canonical observation identity | `(ticker, snapshot_date, workflow, window_sessions, data_as_of_date, config_hash)` |
| Cohort tag | `semantic_compatibility_id` on the row |
| Capture / screen entry | `RecordAccumulationObservationsUseCase` → `AccumulationScreenUseCase.execute` (read-only screen) |
| Request cutoff | `AccumulationScreenRequest.as_of_date`, `window_days` |
| Session resolution | `EffectiveMarketSessionResolver` (as used by backfill) |
| Lean cohort hash | `resolve_lean_semantic_compatibility_id(...)` (backfill composition root) |

---

## What Slice B builds

### New application use case (name locked)

`VerifyStoredSignalObservationUseCase`  
(or `RecomputeStoredSignalObservationUseCase` — pick one; prefer **Verify** so
CLI language stays distinct from retrieval).

**Must not** mutate observations or labels. Screen-only; no `persist()`.

### Selection

Reuse Slice A selection rules **before** recompute:

1. Explicit `observation_captured_at` → that row
2. Else exactly one row for ticker/date → that row
3. Else → `AMBIGUOUS` (same as retrieval); do not recompute

Never call `get_latest`.

### Cohort / config gate (fail closed)

Before running the screen:

1. Resolve **current** lean `semantic_compatibility_id` from the same scoring
   config set the backfill composition root uses.
2. If the stored row has no `semantic_compatibility_id`, or it **differs** from
   current → status `UNREPRODUCIBLE` with reason
   `config_or_code_cohort_mismatch` (include both ids). **Do not** run the
   screen and pretend a drift diff is meaningful.
3. If `config_hash` is empty / row non-canonical → `UNREPRODUCIBLE` /
   `non_canonical_observation`.

Optional hardening (same slice if cheap): also require
`window_sessions` and request `window_days` alignment when rebuilding the
request.

### Local recompute (no network)

Build `AccumulationScreenRequest` for:

- `tickers=(stored.ticker,)`
- `window_days=stored.window_sessions`
- `as_of_date=stored.analysis_as_of or stored.snapshot_date`  
  (prefer `analysis_as_of` when present — that is the recorded decision cutoff)
- thresholds: from the **same** typed/scoring config object used to compute
  the current cohort id (adapter wires; use case receives typed config /
  factory, does not read YAML files)

Wire `SignalEvidenceExecutionContext` with a resolved `EffectiveMarketSession`
for that as-of date (same pattern as backfill). Call
`AccumulationScreenUseCase.execute` only.

If local market/broker data is insufficient to evaluate → `UNREPRODUCIBLE` /
`missing_local_source_data` (machine-readable; include what was missing if the
screen already surfaces it).

### Comparison set (small — do not boil the fingerprint ocean)

Compare **only** these stored-vs-recomputed fields in Slice B:

| Field | Source (stored) | Source (recomputed) |
|---|---|---|
| `score` | `payload.signal.assessment.score` | recomputed assessment score |
| `signal_authority_coverage` | assessment field (legacy fallback only if absent) | same |
| `setup_phase` / readiness phase | fingerprint / candidate path already used at capture | same path on recomputed candidate |
| `fingerprint_digest` | stable hash of canonical fingerprint payload (or the existing fingerprint serialization used for labels) | same digest over recomputed fingerprint |

Do **not** in Slice B:

- Diff all ~90 fingerprint scalars field-by-field
- Diff trade_setup / risk action (unless free and already on the candidate)
- Persist a verify report table
- Attach artifact_identity / git SHA requirements

If any compared field differs → `DRIFT` with a machine-readable
`differences: list[{field, stored, recomputed}]`.  
If all match → `MATCH`.

### Status enum (locked)

```text
AMBIGUOUS          — selection failed (Slice A policy); no recompute
UNREPRODUCIBLE     — cannot meaningfully recompute (cohort / non-canonical / missing local data)
MATCH              — recompute succeeded; compared fields equal
DRIFT              — recompute succeeded; at least one compared field differs
```

Reasons are structured strings / codes, never a single collapsed warning blob.

### CLI (thin adapter)

Keep command name `signal-replay` until CLI restructure.

- Default (no flag): Slice A retrieval — unchanged
- `--verify`: run `VerifyStoredSignalObservationUseCase` after the same
  identity selection inputs (`ticker`, `snapshot_date`, optional
  `--captured-at`)

Print:

- Mode: `VERIFY_LOCAL_RECOMPUTE` (not “replay success”)
- Selected identity (same fields as Slice A)
- Status + reasons
- On `DRIFT`: field diffs
- Footer note: residual risk of post-capture local backfill; not promotion-grade
  bit-identity

Adapter may only: parse flags, wire screen + session resolver + scoring config
→ cohort id, call use case, format output. No cutoff policy in the adapter.

---

## Layer plan

```md
- Domain: small result/value types for verify status + difference records
  (or frozen dataclasses colocated with the use case if they are
  application-only DTOs — prefer application DTO unless reused elsewhere)
- Application: VerifyStoredSignalObservationUseCase (orchestration + compare
  policy + UNREPRODUCIBLE gates). Reuse AccumulationScreenUseCase; do not
  put compare policy in the adapter.
- Infrastructure: not touched (no new tables, no network providers)
- Adapter: signal-replay `--verify` wiring + display only
```

**Semantic Change Classification:** `NON_SEMANTIC` for existing observation/
label meanings — this is a new read-only verify path. Do not bump observation
or label schema versions.

---

## Do Not Interpret This As

- Do not refetch Stockbit/IDX/enrichment APIs for verify.
- Do not build source-snapshot tables, config blob stores, or require
  `application_revision` in Slice B.
- Do not silently select latest among versions.
- Do not persist recomputed rows over the stored observation.
- Do not claim `MATCH` when cohort ids differ.
- Do not fold all failures into one generic “warning”.
- Do not expand the diff to the full fingerprint surface “while we’re here”.
- Do not unblock promotion / patch eligibility from `MATCH` alone (DQ-006+).

---

## Contracts / tests (negative-first)

1. **AMBIGUOUS** with ≥2 versions and no `--captured-at` → no screen call
   (recording fake / spy).
2. **UNREPRODUCIBLE** when stored `semantic_compatibility_id` ≠ current → no
   screen call.
3. **UNREPRODUCIBLE** when local candles insufficient → reason
   `missing_local_source_data`.
4. **MATCH** when screen returns identical score/coverage/phase/fingerprint
   digest to the stored payload (deterministic fakes).
5. **DRIFT** when score (or digest) differs — `differences` lists the field;
   status is `DRIFT` not a warning string.
6. Adapter remains thin: cutoff / cohort / compare decisions live in the use
   case (architecture boundary test).
7. Default CLI path without `--verify` still `RETRIEVAL_ONLY` (Slice A
   regression).

---

## Composition roots to wire

- `src/adapters/cli/analyze_signal_replay_commands.py` only (plus whatever
  factory/helpers backfill already uses to build screen + cohort id — reuse,
  do not duplicate YAML hashing logic in the use case).

---

## Close criteria

- [x] Verify use case + tests above green
- [x] `--verify` CLI path prints status/identity/diffs; default path unchanged
- [x] No new SQLite migrations
- [x] `git diff --check` clean; focused suite green
- [x] DQ-005 criterion “Drift is machine-readable…” marked `[x]` with
      satisfied-notes; residual backfill risk documented
- [x] This plan’s Slice B status → `DONE`

---

## Parked (explicitly out of Slice B)

| Parked item | Wake when |
|---|---|
| Per-source snapshot IDs / immutable input freeze | Promotion needs bit-identical proof |
| Persist verify reports / audit table | Operational need to store verify history |
| Full fingerprint field-by-field diff | Drift triage needs it |
| Internet refetch / live provider verify | Never for this product’s default verify |
| Renaming CLI `signal-replay` → `signal-retrieve` | CLI restructure (`improvement_cli_restructure.md`) |
| Treating `MATCH` as patch/promotion eligibility | DQ-006 + promotion lane |

---

## After implementation — doc update

Update `audit_data_quality.md` DQ-005:

- State: Slice A + Slice B done (raw verify path complete)
- Mark remaining drift criterion `[x]`
- Keep clean-break language; note residual local-backfill limitation

Do not mark DQ-006 unblocked until its own audit criteria are addressed —
Slice B unblocks *starting* DQ-006 discussion, not rubber-stamping readiness.
