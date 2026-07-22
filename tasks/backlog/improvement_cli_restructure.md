# Backlog: CLI command hierarchy restructure

## 1. Task metadata

**Task title:** Restructure signal and accumulation CLI by research vs analyze
**Task type:** Refactor
**Overall priority:** High
**Status:** Done (v1) — 2026-07-22
**Decision:** Implement **this document only** — `research` corpus root + live
`analyze signal inspect`, **clean break** (no aliases, no deprecation window).

**Hard prerequisite:** `DQ-BASELINE-GATE` / DQ-011 (**Done 2026-07-22**).
Sentiment command moves remain gated by DQ-009 (out of v1 scope below).

Freeze corrected behavioral baselines from DQ-011; do not preserve known
data-quality defects during migration. Routing only — no SignalEngine / label
math changes.

**Shipped commits (v1):**

| Slice | What | Notes |
|-------|------|-------|
| CLI-R2 / R4 / R5 / R6 | Remount + docs/cron cutover | `dc93963` |
| CLI-R3 | `research signal capture` + EOD cron uses capture | this change |

## 2. Problem statement

Today’s `saham analyze` mixes unrelated leaves and hides side effects:

```text
signal-inspect / signal-replay / signal-readiness   # read-only (mixed intents)
signal-backfill-observations / signal-labels        # may WRITE
accum-audit                                         # offline eval
audit                                               # sentiment WRITE (separate subject)
```

Objective failures:

1. Corpus work (backfill, labels, replay, readiness, offline eval) is not grouped.
2. Write-producing commands live under `analyze`.
3. `learn` already means the **opening session journal** — overloading it for
   signal corpus persistence is dishonest.
4. Agents misread authority and side effects from the path.

## 3. Chosen command model (clean break)

### Category meanings

| Root | Means | Side effects |
|------|--------|--------------|
| `research` | Quant research corpus + offline study | May persist observations/labels; CSV only when explicit |
| `analyze` | Live / interactive assessment | Read-only for signal inspect in this scope |
| `learn` | Opening session journal (`snapshot`/`track`/`grade`/…) | Unchanged; **not** signal corpus |
| `audit` | Data-quality ops (`audit data …`) | Unchanged |
| `screen` | Live discovery | Unchanged (not authoritative observation capture) |

### Grammar

```text
saham research {subject} {operation}
saham analyze signal inspect …
```

### Canonical v1 surface

```text
saham research signal backfill --universe … --start … --end …
saham research signal labels [SNAPSHOT_DATE] [options]
saham research signal replay TICKER DATE [--verify]
saham research signal readiness --target TARGET
saham research signal capture --contract accumulation-discovery --session DATE --universe …

saham research accumulation evaluate [TICKERS…] [options]

saham analyze signal inspect TICKER [--date DATE] [--window-days N] [--format …] [--db PATH]
```

Use subcommands, not operation-selecting flags. Flags only modify one operation
(e.g. `--generate` on `labels`, `--contract` on `capture`).

**Forbidden forms:**

```text
saham signal --audit
saham analyze signal --replay
saham research --type accumulation
```

### Clean break (mandatory)

- **No aliases.** Old flat paths are **removed** in the same release as the new
  paths land (or in ordered slices that never leave dual public surfaces).
- **No deprecation window.** No hidden redirects, no stderr “use new path” shim.
- **No dual handlers.** One registration per workflow; old Typer names deleted.
- Callers (`install_cron.sh`, docs, tests, agent examples) cut over in the same
  slice that removes the old path.
- `tests/adapters/cli/test_command_contract.py` must list canonical names and
  put retired names in `REMOVED_PATHS` (unknown-command, non-zero exit).

## 4. Current → target (remove left column)

| Remove (retired) | Canonical replacement | Side effects | Status |
|---|---|---|---|
| `analyze signal-inspect` | `analyze signal inspect` | Read-only live | Done |
| `analyze signal-replay` | `research signal replay` | Read-only corpus | Done |
| `analyze signal-readiness` | `research signal readiness` | Read-only corpus | Done |
| `analyze signal-backfill-observations` | `research signal backfill` | Writes observations; optional labels | Done |
| `analyze signal-labels` | `research signal labels` | Summary RO; `--generate*` writes | Done |
| `analyze accum-audit` | `research accumulation evaluate` | Offline eval; CSV only with `--output` | Done |
| *(new)* | `research signal capture` | Writes observations | Done |

**Out of v1 (parked):**

| Current | Later target | Gate |
|---|---|---|
| `analyze audit` (sentiment) | e.g. `research sentiment audit` | DQ-009 |
| Opening `learn *` | optional rename to `session`/`opening` | separate product decision |

**Cron honesty:** EOD corpus writer is
`saham research signal capture --contract accumulation-discovery …`.
`screen accum` remains live discovery only — not observation capture.

## 5. Key principles

1. **Category before subject.** `research` vs `analyze` vs `learn` encode real jobs.
2. **One public path per workflow.** Clean break — no alias dual surface.
3. **Names describe artifacts.** `inspect` = live; `replay` = stored; `evaluate` = offline outcomes; `backfill`/`labels`/`capture` = corpus writes.
4. **No hidden writes under `analyze`.** Corpus persistence lives under `research`.
5. **Adapters stay thin.** Routers register; handlers parse/map/render; use cases own policy.
6. **Deterministic behavior unchanged.** Discoverability/routing only.
7. **Agent discoverability is a contract.** Help states artifact, side effects, local/network, read vs write.
8. **Program clean-break policy applies** to removed command identities (see `AGENT_QUICKSTART.md` / signal evidence program).

## 6. Ordered implementation backlog

### CLI-R0 — Amend contracts / docs pointers (this file)

**State:** Done (2026-07-22).
Update program/index pointers that still say `learn signal` for corpus work.

### CLI-R1 — Freeze checklist on behavior (not old names)

**Priority:** P0
**Depends on:** DQ-011
**State:** Done — DQ-011 contracts remounted to canonical paths with `dc93963`.

**Outcome:** Args, exit codes, stdout/stderr, read/write assertions, JSON roots
remain locked while routing changes.

Reuse DQ-011 goldens; remount tests to new paths in the same PR as each removal.

### CLI-R2 — Introduce `research` + `research signal` (corpus commands)

**Priority:** P0
**Depends on:** CLI-R1 mindset / DQ-011
**State:** Done (`dc93963`).

**Mount (reuse existing handlers/use cases):**

```text
saham research signal backfill …
saham research signal labels …
saham research signal replay …
saham research signal readiness …
```

**Same PR must:**

- Delete `analyze signal-backfill-observations`, `signal-labels`, `signal-replay`,
  `signal-readiness` registrations.
- Update `EXPECTED_COMMANDS` / `REMOVED_PATHS`, all CLI tests, cron, and docs
  that referenced the old paths.
- Help: `Research corpus for SignalEngine observations and labels. May persist.`

**Do not:** change observation identity, label math, or add aliases.

**Acceptance:**

- [x] `saham research signal --help` lists the mounted ops (no retired flat names).
- [x] Retired paths fail unknown-command.
- [x] DQ-011 behavioral contracts still pass on new paths.
- [x] Summary-only `labels` remains read-only; `--generate*` writes only labels.
- [x] `backfill` write assertions unchanged in meaning.

### CLI-R3 — `research signal capture` (when producer is ready)

**Priority:** P0 after CLI-R2 (may be same release if use case already callable)
**Depends on:** application capture use case for `accumulation-discovery`
**State:** Done (2026-07-22) — reuses `RecordAccumulationObservationsUseCase`
via shared `run_signal_observation_corpus_write` (single-session backfill
composition); EOD cron cut over to capture.

```text
saham research signal capture --contract accumulation-discovery --session DATE --universe …
```

Universe-driven, idempotent; not single-ticker. No provisional
`legacy-accumulation-candidates` bridge in this clean-break plan.

**Acceptance:**

- [x] help states written tables (`candidate_observations`; not labels).
- [x] cron uses this path for EOD observation write.
- [x] negative tests: unsupported contract / invalid session do not write;
      `analyze signal inspect` remains read-only.

### CLI-R4 — `research accumulation evaluate`

**Priority:** P0
**Depends on:** CLI-R2 pattern proven (may parallelize after R2 starts)
**State:** Done (`dc93963`).

```text
saham research accumulation evaluate [TICKERS…] [existing options]
```

**Same PR:** delete `analyze accum-audit`; update tests/docs/cron if any.

Preserve DESCRIPTIVE claim stamps, no DB writes, CSV only with `--output`.

### CLI-R5 — Live `analyze signal inspect`

**Priority:** P0
**State:** Done (`dc93963`).

```text
saham analyze signal inspect TICKER …
```

**Same PR:** delete `analyze signal-inspect`; `analyze signal --help` lists
**only** `inspect` (no backfill/labels under analyze).

Help: `Read-only live SignalEngine assessment from local data.`

### CLI-R6 — Docs / agent / cron sweep

**Priority:** P0
**Depends on:** CLI-R2…R5 as each lands
**State:** Done for remount (`dc93963`); capture cron/docs updated with CLI-R3.

Repository search: retired strings only in `REMOVED_PATHS`, historical commits,
and explicit “removed commands” notes — **not** in live examples.

### Parked (not v1)

| Item | Why |
|------|-----|
| Sentiment → `research sentiment audit` | Needs DQ-009 |
| Rename opening `learn` → `session`/`opening` | Separate UX decision |
| `risk` / `compare` / `swing` regroup | Prove `research` pattern first |
| Named-setup capture contract | Product trigger (`NAMED-SWING-SETUP-CAPTURE`) |

## 7. Architecture impact

| Question | Answer |
|---|---|
| Domain touched? | No |
| Application behavior? | No (reuse use cases) |
| Adapter? | Yes — new `research` routers; delete old registrations |
| Infrastructure? | No except import wiring |
| Persistence schema? | No |
| Aliases / compatibility shims? | **No** |

```text
Layer plan:
- Domain: not touched
- Application: not touched (unless capture wiring already exists)
- Infrastructure: not touched
- Adapter: research + analyze.signal routers; remove retired commands
- Documentation: canonical paths only; cron cutover
```

## 8. AI usage

No AI in runtime. Offline wherever the current command is offline.

## 9. Risk / signal / evidence authority

Must **not** change scoring, RiskEngine, TradeSetup, evidence PRODUCTION registry,
observation/label definitions, or readiness promotion rules. Routing only.

## 10. Persistence invariants

- `analyze signal inspect` — no observation/label writes
- `research signal replay` / `readiness` — no writes
- `research signal backfill` — observation writes (+ optional labels) as today
- `research signal labels` — writes only with explicit generate flags
- `research signal capture` — observation writes; **no** label generation
- `research accumulation evaluate` — no DB writes; CSV only with `--output`

## 11. Global negative requirements

Do Not Interpret This As:

- Do not add aliases, hidden redirects, or a deprecation dual surface.
- Do not put corpus writes under `learn` or `analyze`.
- Do not move opening `learn snapshot|track|…` under `research`.
- Do not treat `screen accum` as canonical observation capture.
- Do not use flags to select distinct operations.
- Do not change output schemas, scoring, or persistence identity as “cleanup.”
- Do not ship new paths while old public paths still work.
- Do not include sentiment rename in v1 without DQ-009.

## 12. Verification

Each slice:

1. Command contract tests for **canonical** paths only.
2. `REMOVED_PATHS` assertions for retired names.
3. Reused use-case tests still green.
4. Negative: forbidden writes / unknown old commands.
5. stdout/stderr separation.
6. Help discovery.
7. Architecture boundary tests.
8. `git diff --check`.

Smoke matrix (canonical names):

| Command | Success | Invalid | No data | JSON | Write assertion |
|---|---:|---:|---:|---:|---:|
| `analyze signal inspect` | ✓ | ✓ | ✓ | ✓ | no writes |
| `research signal replay` | ✓ | ✓ | ✓ | if any | no writes |
| `research signal readiness` | ✓ | ✓ | ✓ | ✓ | no writes |
| `research signal backfill` | ✓ | ✓ | ✓ | ✓ | observation writes |
| `research signal capture` | ✓ | ✓ | ✓ | ✓ | observation writes; no labels |
| `research signal labels` summary | ✓ | ✓ | ✓ | ✓ | no writes |
| `research signal labels --generate*` | ✓ | ✓ | ✓ | ✓ | label writes |
| `research accumulation evaluate` | ✓ | ✓ | ✓ | ✓ | no DB; CSV if `--output` |

## 13. Global completion gate (v1)

- [x] All v1 canonical paths exist with accurate help.
- [x] All mapped retired paths are gone (`REMOVED_PATHS`).
- [x] Corpus writes are only under `research`; live inspect under `analyze signal`.
- [x] Opening `learn` unchanged and not used for signal corpus.
- [x] Cron/docs/tests use canonical paths only.
- [x] No engine/scoring/persistence semantic change.
- [x] Focused + contract suites pass; `git diff --check` clean.
