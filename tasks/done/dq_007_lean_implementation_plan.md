# DQ-007 lean implementation plan (amended 2026-07-22)

**Status:** DONE (D7-1 + D7-2 implemented 2026-07-22). Parked items unchanged.

Companion to `tasks/done/audit_data_quality.md` → DQ-007 and its "Lean
inspection amendment (2026-07-22)". Prove that a read-only inspector explains
the **same** canonical SignalEngine calculation screen/swing use — not a
resurrected six-factor audit or a second composite.

## Guiding decision

Implement this option only.

> Deliver one read-only inspection use case that resolves an effective session,
> builds `CanonicalSignalEvidenceInput` via an **existing** evidence assembly
> path, calls `SignalEngine.evaluate_with_context`, and exposes provenance /
> availability / authority / readiness / constraints / diagnostics / final
> assessment. No parallel scorer. No observation/label/tuning writes. Permanent
> CLI hierarchy rename stays with CLI-002.

**Why (codebase-grounded):**

- `LIVE-CONTRACT-GATE` is already **satisfied** (including
  `RETIRE-LEGACY-SIX-FACTOR-BASELINE`). Legacy `signal-audit` /
  `AssessSignalUseCase` are gone; there is **no** live inspect replacement yet.
- Screen and swing already share config → `SignalEngine` →
  `AssessSignalEvidenceUseCase` and the `CanonicalSignalEvidenceInput` shape.
  Evidence **assembly** differs (screen is flow-only by design; swing may
  include setup). A third assembly path would be the failure mode.
- `signal-replay --verify` proves **stored observation** reproducibility, not
  live “engine at session T” explainability. Reuse builders/engine; do not
  treat verify as the DQ-007 artifact.
- `analyze swing --explain` is live-today, couples TradeSetup/risk, and lacks
  `--date` PIT. Do not grow it into the inspector.
- `SqliteSignalCoverageProvider` is enrichment-cache era taxonomy and unwired
  after audit removal — polish is optional, not the scorer-identity proof.

---

## Vet findings → backlog revisions

| Current backlog ask | Verdict | Lean action |
|---|---|---|
| Same prepared input + same scorer as screen/swing; no parallel composite | Keep — **missing** | Slice D7-1 use case |
| Golden calculations within tolerances | Keep | D7-1 golden against `AssessSignalEvidenceUseCase` / known vectors |
| `--date T` is point-in-time (no latest enrichment join) | Keep | D7-1 session resolver + fail-closed / unavailable for future-only data |
| Missing data cannot inflate authority/readiness | Keep | D7-1 negative tests |
| No six-factor / `factors.*` surface in output | Keep | D7-1 serialization guards |
| Expose session, provenance, availability, coverage, readiness, constraints, diagnostics, final assessment | Keep (canonical groups) | D7-1 DTO wraps `AssessSignalResponse` + session/provenance |
| “Every factor” source date/value/unit/freshness panels | **Stale wording** | Reinterpret as **setup/flow groups + diagnostic slots** with provenance/availability; do not rebuild six enrichment-factor UI |
| Validate coverage provider SQL (rows/usable/unique tickers) | **Overscoped now** | Park `--coverage` / provider taxonomy rewrite |
| Permanent `saham analyze signal inspect` hierarchy | **Owned by CLI-002** | Thin provisional CLI only in D7-2 |
| Dual screen+swing product UX in one command | **Overscoped now** | First contract mode only (see below) |
| Rename `legacy_conditioned_score` | Hygiene | Park (document: regime conditioning ≠ six-factor) |

---

## What already exists (reuse)

| Piece | Location |
|---|---|
| Shared engine facade | `src/application/services/signal_engine.py` → `evaluate_with_context` |
| Factory / config | `signal_engine_factory.py`, `signal_engine_config_loader.py`, resolver |
| Canonical input VO | `CanonicalSignalEvidenceInput` |
| Screen assembly | `AccumulationCandidateSignalAssessor` (flow-only) |
| Swing assembly | `SwingAnalysisDecisionComposer._build_canonical_evidence` |
| Session contract | `EffectiveMarketSessionResolver` (DQ-002) |
| Availability assembler | `EvidenceSourceAvailabilityAssembler` |
| Core golden math tests | `tests/application/use_case/test_signal_evidence_*.py` |
| Legacy absence guards | `tests/adapters/cli/test_command_contract.py`, config resolver fail-closed |
| Verify (related, not inspect) | `VerifyStoredSignalObservationUseCase` |

---

## First contract mode (implement this option only)

**Mode `accumulation-flow` (default for D7-1):**

- Assemble evidence the same way the accumulation screen assessor does for one
  ticker (flow confirmation; setup intentionally absent).
- Call the same `SignalEngine.evaluate_with_context`.
- Document explicitly that screen is flow-only by design; inspection matching
  that boundary is honest, not incomplete.

**Optional follow-on (only if D7-1 is green and cheap):** mode
`swing-setup` reusing swing evidence builders — still no third scorer. If it
grows into TradeSetup/risk orchestration, stop and park behind a named slice.

Do **not** invent a third “inspect-only” evidence builder.

---

## Slice D7-1 — Read-only inspect use case + shared-path goldens

**Status:** DONE

**Goal:** Close scorer-identity, PIT, missing-data, and no-six-factor criteria
without a CLI platform.

**Layer plan:**
```md
- Domain: not touched (reuse CanonicalSignalEvidenceInput / response VOs)
- Application: new InspectCanonicalSignalUseCase (name flexible) — session
  resolve, reuse existing assembly, evaluate_with_context, read-only DTO
- Infrastructure: reuse factory/config/session ports only; no new schema
- Adapter: not touched in D7-1 (or JSON harness in tests only)
```

**Contracts (implement this option only):**

1. **Shared path**
   - Input: ticker + optional as-of date + contract mode (`accumulation-flow`).
   - Resolve `EffectiveMarketSession` for that date (same DQ-002 contract as
     backfill/verify).
   - Build `CanonicalSignalEvidenceInput` via existing screen assessor path
     (or extracted shared helper already used by screen — no fork of scoring).
   - Score only through `SignalEngine.evaluate_with_context`.
   - DTO embeds/wraps the resulting `AssessSignalResponse` plus effective
     session, provenance, and availability from the canonical input.

2. **Point-in-time honesty**
   - Historical `--date T` must not silently join future/current-only
     enrichment. Prefer fail-closed or explicit UNAVAILABLE / provenance notes
     aligned with existing evidence availability semantics.

3. **Authority honesty**
   - Missing/unavailable evidence must not increase
     `signal_authority_coverage`, setup readiness, or directional conviction
     relative to the empty/missing baseline for that vector.

4. **No parallel / legacy composite**
   - No second score formula.
   - Serialized output must not expose `factors.*`, six-factor weights, or
     resurrected `AssessSignalUseCase` fields.
   - `legacy_conditioned_score` (if present) is regime conditioning on the
     canonical path — document in notes; do not treat as six-factor revival.

5. **Read-only**
   - No observation, label, tuning, promotion, or config writes.

**Negative-first tests:**

- Inspector score/coverage/setup_phase match a direct
  `AssessSignalEvidenceUseCase` / engine call on the same
  `CanonicalSignalEvidenceInput` within declared tolerances.
- Missing evidence cannot raise authority coverage vs empty baseline.
- As-of date cannot consume rows with source dates after the resolved session
  cutoff (or must mark unavailable — assert the chosen fail-closed behavior).
- Output JSON/dict has no `factors` / six-factor weight surface.
- Use case performs no repository `save*` / write calls (fake repos assert).

**Semantic Change Classification:** `NON_SEMANTIC` for live screen/swing
scores if the inspector only reuses existing paths. If assembly extraction
accidentally changes screen/swing behavior, stop — that is
`SEMANTIC_ENGINE` / `EVIDENCE_CONTRACT` and needs an explicit decision.

**Checkpoint:** stop for review after D7-1 before provisional CLI.

---

## Slice D7-2 — Thin provisional CLI + terminology identity

**Status:** DONE

**Goal:** Make the verified use case operable without waiting for CLI-002
hierarchy work; lock table/JSON/DTO terminology.

**Layer plan:**
```md
- Domain: not touched
- Application: not touched (unless tiny DTO field aliases for display)
- Infrastructure: not touched
- Adapter: thin provisional command — parse, wire, call use case, format, map errors
```

**Contracts:**

1. **Provisional command** (temporary name OK), e.g.
   `saham analyze signal-inspect TICKER [--date DATE] [--db PATH]`
   - Adapter stays thin: no cache/PIT/score policy in CLI.
   - Document that CLI-002 will remount as `saham analyze signal inspect`.

2. **Terminology identity**
   - Table, JSON, and DTO use the same names for score,
     `signal_authority_coverage`, readiness, constraints, diagnostics.
   - Do not invent “confidence” aliases that diverge from the response VO.

3. **Still no writes**; still no coverage-provider product unless already free.

**Negative-first tests:**

- CLI smoke: exits 0 on fixture/fake path; JSON keys match DTO.
- Removed `signal-audit` remains absent (`test_command_contract`).
- Provisional command does not register write side effects.

**Close:** focused + related signal-evidence tests green; `git diff --check`.

---

## Parked (explicit)

| Parked | Wake when |
|---|---|
| CLI-002 permanent `analyze signal inspect` group/router | After DQ-007 Done |
| Enrichment `--coverage` / rewrite `SqliteSignalCoverageProvider` taxonomy | Operator needs cache inventory, not scorer explain |
| Dual-mode product UX (screen + swing in one polished command) | After first mode proven; or named follow-on slice |
| Growing `analyze swing --explain` into the inspector | Never as DQ-007 substitute |
| Treating `signal-replay --verify` as inspection | Different artifact (stored observation) |
| Renaming `legacy_conditioned_score` | Doc/UX hygiene task |
| DQ-008 accumulation historical evaluation | After DQ-007 Done |
| Observation/label/tuning/promotion writes | Explicitly forbidden |

---

## After each slice — doc update

- Mark closed DQ-007 acceptance criteria `[x]` with satisfied-notes.
- Update this plan’s slice `Status`.
- Keep DQ-007 State = Done only when D7-1 + D7-2 close lean criteria.
- Do not mark parked criteria done.
- Do not claim `DQ-BASELINE-GATE` complete (still needs DQ-008 + DQ-010/011
  per program gate text).
