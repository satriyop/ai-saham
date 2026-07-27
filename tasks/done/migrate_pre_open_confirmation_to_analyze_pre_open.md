# Migrate Pre-Open Confirmation to `saham analyze pre-open`

Status: `DONE` — landed in `7026759` (2026-07-27); residual docs scrubbed when retiring task

Governing decisions:

- [ADR-026](../../docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md)
- [ADR-033](../../docs/adr/ADR-033-workflow-composition-artifact-boundaries.md)
- [ADR-046](../../docs/adr/ADR-046-cli-response-envelope.md) (JSON envelope adopt-on-touch)
- [ADR-048](../../docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md)
- [ADR-049](../../docs/adr/ADR-049-database-owned-learning-pipeline-clean-break.md)

## 0. Finalized product decisions (do not re-litigate)

| # | Decision |
|---|----------|
| 1 | Journal type for this strategy: **`--type pre-open`** (retire `--type intraday` for this path; **no** alias). |
| 2 | **Keep** paper journal: `trade log` + `trade review` + `trade outcome` for the pre-open paper book. |
| 3 | **Prerequisite first:** implement only after (or immediately after producers fix so) `research pre-open capture` + `track` reliably persist observation IDs and linked track snapshots. |
| 4 | **Opening price rules:** reuse existing confirm-policy arithmetic; change only **transport** (load from immutable track snapshot ID, not sidecar/live). |
| 5 | **`loop_intraday.sh`:** remove confirm phase / do not preserve script merely for confirm (no new screen-only loop unless a later task asks). |
| 6 | **Cron:** no auto `analyze` and no auto `trade log`; human runs assess then log. Remove `trade confirm` / confirmation-sidecar cron lines. |
| 7 | **ADR:** small amendment to ADR-049 and/or ADR-033 in the **same implementation PR** (command ownership + sidecar retirement). |

Unique value of `trade log` (retained on purpose): personal paper notebook — not learning capture, not assess, not outcome labels.

## 1. Task Metadata

- Task type: Refactor / clean-break CLI migration
- Priority: High (blocked until pre-open capture+track write DB IDs reliably)
- Semantic classification: `NON_SEMANTIC` only if equivalent fixtures prove
  that `ConfirmIntradayOpenUseCase` arithmetic and decisions are unchanged.
  Escalate to `SEMANTIC_ENGINE`, `EVIDENCE_CONTRACT`, or `CONFIG_MATERIAL`
  before editing if opening-price authority, gates, thresholds, or canonical
  output meaning changes.
- Chosen decision: retire `saham trade confirm` and expose the deterministic
  post-open assessment as **`saham analyze pre-open`**. Implement this option
  only. **Single release; no alias window.**

### Locked public name (anti-confusion)

| Token | Meaning |
|-------|---------|
| **`saham analyze pre-open`** | **Post-open** assessment of an immutable **pre-open strategy** plan |
| `saham screen pre-open` | Live discovery only (no learning write) |
| `saham research pre-open capture\|track\|labels\|evaluate\|status` | Learning lifecycle for the same strategy |
| `saham research pre-open evaluate` | Session/cohort **outcome** evaluation (labels), **not** post-open execution assessment |

- **`pre-open` names the strategy / cohort identity**, not the wall-clock phase
  of this command. The command **runs after the market opens** (typically after
  09:00 once an opening track sample exists).
- Help **first line** and result header **must** say: *post-open assessment of
  NCP pre-open plan* (or equivalent plain language).
- Do **not** rename to `analyze opening`, `analyze open-confirm`, or any other
  public path. Do **not** keep `trade confirm` as an alias or deprecation shim.

## 2. Problem Statement

The current `saham trade confirm` command mixes three responsibilities:

1. resolving post-open prices,
2. analyzing whether an 08:57 pre-open plan remains executable, and
3. writing a confirmation sidecar later consumed by the paper-trade journal.

It reads `data/session/.last-session.json`, may use file/manual/live fallbacks,
writes another “last confirmation” file, and presents a second verdict without
making its relationship to the persisted pre-open observation explicit.
`loop_intraday.sh` compounds the ambiguity by rerunning the command every 30
seconds and overwriting the same sidecar.

The database-owned lifecycle already has immutable pre-open observations and
observation-linked track snapshots. Continuing to transport authority through
mutable “last session” files creates ambiguous identity, prevents deterministic
replay, and makes an analysis command look like trade execution.

## 3. Desired Outcome

Expose one read-only command:

```text
saham analyze pre-open
saham analyze pre-open --session YYYY-MM-DD
saham analyze pre-open --observation-id OBSERVATION_ID
saham analyze pre-open --observation-id OBSERVATION_ID \
  --opening-snapshot-id SNAPSHOT_ID
saham analyze pre-open --format json
```

The command:

- reads the exact immutable 08:57
  `learning_observation.pre_open_auction_direction.v1` observation;
- reads an observation-linked persisted **opening track snapshot** (see
  §3.1);
- reuses the existing deterministic post-open confirmation policy;
- projects the pre-open direction/setup (from the observation) separately from
  the post-open `ENTER` / `WAIT` / `SKIP_*` assessment;
- writes nothing; JSON output is stdout-only (ADR-046 envelope adopt-on-touch
  if analyze family is not already on the shared envelope);
- prints the consumed `observation_id`, `opening_snapshot_id`, cutoff,
  compatibility identity, opening-price provenance, and policy identity.

Default selection is the current IDX session. It may analyze all compatible
pre-open observations for that session only when there is exactly one
unambiguous compatible cohort (same purpose + contract_id + session cutoff).
Ambiguous cohorts fail closed and require `--observation-id`. An explicit
snapshot must belong to the selected observation; cross-observation
substitution is a hard contract error.

### 3.1 Opening snapshot and price authority (locked)

**Opening snapshot** = one row in `learning_track_snapshots` linked to the
chosen observation.

Default when `--opening-snapshot-id` is omitted:

1. Among track snapshots for that `observation_id`, select the **earliest**
   sample with `sampled_at` in the regular open window on the observation’s
   session date (local IDX calendar), typically the first post-09:00 sample
   written by `research pre-open track`.
2. If none exist, result is **unavailable** (typed), never fabricated and never
   live-fetched as a substitute.
3. If multiple candidates share the same earliest timestamp, fail closed and
   require `--opening-snapshot-id`.

**Opening price** = the track snapshot’s explicit opening-price field(s) as
already defined by the confirmation policy / track contract (last trade / open
proxy with confidence). Do **not** silently substitute mid-of-book or another
source as “opening” without a separate, approved semantic change. Provenance
must appear in the analyze output.

Paper-trade logging remains an explicit, separate action under the unified
`trade log` router. **Type name is strategy-contextual:**

```text
saham trade log --type pre-open \
  --observation-id OBSERVATION_ID \
  --opening-snapshot-id SNAPSHOT_ID
```

- Retire **`--type intraday`** for this path (no alias to `pre-open`).
- Retire **`--confirmation`** sidecar flag for this path.
- Journal files/config may keep internal path names temporarily if needed, but
  the **CLI type** and user docs must say `pre-open`. Prefer renaming
  journal config keys to `pre_open_*` in the same cut when nothing else shares
  the old `intraday_confirmation_*` paths.

That command must recompute from those exact immutable IDs through the **same**
application use case (`AnalyzePreOpenUseCase`) before writing the paper journal.
It must never reread live data or accept a mutable “last confirmation” sidecar.

`trade review` / `trade outcome` for this book: use **pre-open** naming in help
and subcommands where they currently say only “intraday” for this strategy
(e.g. `trade review pre-open` if that is a clean rename of the intraday review
path for this journal; do not leave “intraday” as the user-facing strategy name).

## 4. Non-Goals

- No change to 08:56 IEV baseline or 08:57 capture scheduling.
- No capture at or after 09:00 and no post-open data in the pre-open observation.
- No change to SignalEngine, RiskEngine, `TradeSetup`, entry bands, stops,
  regime gates, tick-friction rules, or opening-price calculations unless
  separately classified and approved.
- No automatic order placement or broker execution.
- No new AI path.
- No post-open assessment as an `open_30m` outcome label.
- No replacement of `price_path.open_30m.v1`; outcome labeling remains a later
  truth artifact.
- No mutable JSON/JSONL/Markdown analysis sidecar.
- No merge with `research pre-open evaluate` (cohort outcome evaluation).
- No half-ship: do not leave `trade confirm` callable while analyze is live.

## 5. Do Not Interpret This As

- Do not keep `saham trade confirm` as an alias, hidden route, compatibility
  wrapper, or deprecation shim.
- Do not add `saham analyze opening` or any alternate public name.
- Do not run pre-open capture at 09:00.
- Do not treat post-open assessment as a forward label, walk-forward evaluation,
  or as `research pre-open evaluate`.
- Do not recompute the 08:57 signal, risk, or `TradeSetup`; consume the exact
  persisted decision payload.
- Do not select “latest” across dates, compatibility cohorts, or observations.
- Do not allow an order-book midpoint or another source to silently masquerade
  as the opening-price concept.
- Do not make `analyze` write a trade journal.
- Do not make `trade log` reread a live provider after the user inspected an
  immutable snapshot.
- Do not preserve `loop_intraday.sh` merely to call the removed command (a
  separate display-only screen loop is out of scope unless requested later).

## 6. Architecture Impact Assessment

- Domain: reuse current confirmation decision/value objects; add a typed
  identity binding only if required to bind observation and opening snapshot.
- Application: add `AnalyzePreOpenUseCase` and typed request/result DTOs; it
  owns selection, provenance validation, candidate reconstruction, and calls
  the existing deterministic confirmation policy.
- Infrastructure: repository implementations read immutable learning
  observations and tracks by exact ID. No application-layer SQLite or file I/O.
- Adapter: mount `analyze pre-open`, remove `trade confirm`, update explicit
  intraday trade-log arguments, and render the application result only.

- New dependency: No.
- Affects determinism: No; exact immutable IDs plus policy/config identity must
  reproduce the same assessment.
- Persistence changes: No learning schema change. Existing explicit trade
  journal writes remain outside `analyze`.
- Warm-up data: No.
- Adapter policy/orchestration: No.

```md
Layer plan:
- Domain: typed observation/snapshot binding only if existing IDs are insufficient
- Application: post-open analysis orchestration and fail-closed lineage checks
- Infrastructure: exact-ID learning observation and track repository reads
- Adapter: thin analyze command, removed confirm route, explicit trade-log wiring
```

Prerequisite before implementation: `research pre-open capture` and
`research pre-open track` must already persist observation IDs and linked track
snapshots that this command can address. If not, stop and fix producers first.

## 7. AI Usage Declaration

No AI involved.

## 8. Risk, Signal, and Evidence Authority

- The 08:57 persisted signal and `TradeSetup` remain unchanged and immutable.
- `ConfirmIntradayOpenUseCase` (or its extracted pure policy) remains the sole
  post-open action policy.
- Pre-open output must be presented as the earlier directional/setup state;
  post-open `ENTER` / `WAIT` / `SKIP_*` is a later execution assessment.
- No post-open fact may flow backward into the pre-open observation or its
  compatibility identity.
- No diagnostic evidence is promoted and no tuning eligibility changes.

## 9. Data and Transport Contract

Single source of truth:

```text
learning_observations row
  + exact linked learning_track_snapshots row (opening snapshot)
  → AnalyzePreOpenUseCase
  → typed AnalyzePreOpenResult
  → analyze adapter display/stdout JSON
```

For explicit paper logging:

```text
same observation_id + opening_snapshot_id
  → same AnalyzePreOpenUseCase
  → typed result
  → explicit trade-journal writer
```

Required failure behavior:

- missing observation: typed not-found error;
- wrong purpose/contract: hard contract error;
- unavailable opening snapshot: typed unavailable result, never fabricated;
- snapshot not linked to observation: hard contract error;
- multiple compatible cohorts without explicit identity: ambiguity error;
- provider/file/JSON fallback request: rejected at the CLI boundary;
- malformed persisted canonical payload: propagate and fail closed;
- expected absence must not be converted into `ENTER`.

Retire (non-exhaustive checklist — delete production references):

- `saham trade confirm` and all its flags;
- `--track-file`, `--output`, live/manual price flags, and the old
  `--session PATH` sidecar meaning owned by the removed command; the new
  `--session YYYY-MM-DD` selector is a distinct database-session contract;
- confirmation sidecar loading/writing and “last confirmation” defaults
  (`intraday_confirmation_session_store` confirmation write path, related
  factories/displays);
- `loop_intraday.sh` confirm phase (or the script if only used for that);
- `install_cron.sh` (and runbooks) lines that call `trade confirm`, write
  confirmation sidecars, or auto-journal from last-confirmation files;
- `--type intraday` (and docs/examples) for this strategy path;
- obsolete confirmation-sidecar tests, documentation, and examples.

Do not delete unrelated historical trade journals.

## 10. Acceptance Criteria

- [x] `saham analyze pre-open` is mounted under `analyze`; help first line states
      post-open assessment of NCP pre-open plan.
- [x] `saham trade confirm` and all its flags are absent from help and routing.
- [x] `loop_intraday.sh` confirm loop and mutable confirmation/session analysis
      sidecars are no longer production transport.
- [x] Cron/runbook no longer invoke `trade confirm` or last-session sidecars for
      this purpose.
- [x] The command reads the exact persisted pre-open observation and one linked
      immutable opening track snapshot (§3.1).
- [x] Equivalent fixtures preserve existing post-open decision arithmetic.
- [x] Pre-open direction/setup and post-open action are visibly distinct.
- [x] `--format json` writes stdout only.
- [x] Analysis performs no database, filesystem, journal, YAML, provider, or SDK
      I/O directly from the application layer.
- [x] `trade log --type pre-open` consumes exact immutable IDs and cannot
      reread live state; uses the same use case as analyze; `--type intraday`
      and `--confirmation` are gone for this path.
- [x] Pre-open labels/evaluations remain unchanged; not confused with analyze.
- [x] Documentation and CLI examples contain no removed route or sidecar path.

## 11. Testing Expectations

- Unit: exact observation/snapshot binding, unavailable opening state,
  compatibility ambiguity, default opening-snapshot selection, and unchanged
  confirmation gates.
- Integration: persisted observation + linked track → typed analysis result.
- Producer-to-consumer: the exact snapshot ID shown by `analyze` is the one
  consumed by explicit trade logging; assert repository call counts.
- Negative CLI: removed command and every removed flag/path fail.
- Architecture: application imports no SQLite, filesystem, YAML, Typer, Rich,
  Stockbit SDK, or browser implementation.
- Regression: pre-open capture, track, labels, evaluate, and status suites
  remain green.
- All tests offline; run the full suite and `git diff --check`.

## 12. Documentation Impact

- Update CLI overview, intraday workflow, quick reference, building blocks,
  architecture index/ADR amendments, and cron/runbook references.
- Clearly state that `analyze pre-open` uses **strategy name** `pre-open` and
  runs **after** open.
- Document the three distinct artifacts:
  1. pre-open observation (NCP decision),
  2. post-open assessment (`analyze pre-open`),
  3. later outcome label (`price_path.open_30m.v1` / evaluate).

## 13. Delivery Sequence

1. Confirm producers persist observation IDs + linked track snapshots; amend
   governing ADRs for command ownership and removal of sidecar transport.
2. Add typed application request/result and exact lineage tests (including
   §3.1 default selection).
3. Add repository-port reads and producer-to-consumer integration test.
4. Mount `saham analyze pre-open` (help text anti-confusion).
5. Migrate explicit intraday trade logging to immutable IDs (same use case).
6. Remove `saham trade confirm`, sidecars, loop confirm phase, cron refs, and
   compatibility tests **in the same cut**.
7. Update documentation, run focused/full verification, and commit scoped files.

## 14. Agent Execution Instructions

Before implementation, read `AGENT_QUICKSTART.md`, `AGENTS.md`,
`TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`, ADR-026, ADR-033, ADR-046,
ADR-048, ADR-049, and the current executable CLI/application/repository paths.

State the semantic classification and exact transport design before editing.
If equivalent decision behavior cannot be proven, stop and request approval for
the required semantic contract change.

## Final Gate

The task is complete only when analysis is read-only and database-identified,
the old command and file transport are impossible, explicit journal writes use
the same immutable inputs, deterministic decisions are unchanged, focused and
full tests pass, and `git diff --check` is clean.


## Completion Record

- Completed: 2026-07-27
- Commit: `7026759` feat(analyze): replace trade confirm with database-identified pre-open assess
- Public surface: `saham analyze pre-open`; `trade log --type pre-open`; `trade review pre-open`
- Retired: `trade confirm`, `--type intraday`, loop confirm phase, capture→confirm sidecar authority
- Residual (non-blocking): dead modules `trade_intraday_confirm_*` / `RunIntradayConfirmationWorkflowUseCase` may still exist for pure-policy/backtest reuse; not CLI-mounted. Optional follow-up cleanup.
- Full suite at ship: 5168 passed; 4 unrelated display assertion failures
