# Migrate Pre-Open Confirmation to `saham analyze pre-open`

Status: `BACKLOG`

Governing decisions:

- [ADR-026](../../docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md)
- [ADR-033](../../docs/adr/ADR-033-workflow-composition-artifact-boundaries.md)
- [ADR-048](../../docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md)
- [ADR-049](../../docs/adr/ADR-049-database-owned-learning-pipeline-clean-break.md)

## 1. Task Metadata

- Task type: Refactor / clean-break CLI migration
- Priority: High
- Semantic classification: `NON_SEMANTIC` only if equivalent fixtures prove
  that `ConfirmIntradayOpenUseCase` arithmetic and decisions are unchanged.
  Escalate to `SEMANTIC_ENGINE`, `EVIDENCE_CONTRACT`, or `CONFIG_MATERIAL`
  before editing if opening-price authority, gates, thresholds, or canonical
  output meaning changes.
- Chosen decision: retire `saham trade confirm` and expose the deterministic
  post-open assessment as `saham analyze pre-open`. Implement this option only.

The name `pre-open` identifies the originating strategy and persisted 08:57
observation. The command itself runs after the market opens; its help and output
must state that explicitly. Do not rename it to `analyze opening`.

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
- reads an observation-linked persisted opening snapshot;
- reuses the existing deterministic post-open confirmation policy;
- projects the pre-open direction/setup separately from the post-open
  `ENTER` / `WAIT` / `SKIP_*` assessment;
- writes nothing; JSON output is stdout-only;
- prints the consumed `observation_id`, `opening_snapshot_id`, cutoff,
  compatibility identity, opening-price provenance, and policy identity.

Default selection is the current IDX session. It may analyze all compatible
pre-open observations for that session only when there is exactly one
unambiguous compatible cohort. Ambiguous cohorts fail closed and require
`--observation-id`. An explicit snapshot must belong to the selected
observation; cross-observation substitution is a hard contract error.

Paper-trade logging remains an explicit, separate action:

```text
saham trade log --type intraday \
  --observation-id OBSERVATION_ID \
  --opening-snapshot-id SNAPSHOT_ID
```

That command must recompute from those exact immutable IDs through the same
application use case before writing the existing trade journal. It must never
reread live data or accept a mutable “last confirmation” sidecar.

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

## 5. Do Not Interpret This As

- Do not keep `saham trade confirm` as an alias, hidden route, compatibility
  wrapper, or deprecation shim.
- Do not add `saham analyze opening`; the locked public name is
  `saham analyze pre-open`.
- Do not run pre-open capture at 09:00.
- Do not treat post-open assessment as a forward label or walk-forward
  evaluation.
- Do not recompute the 08:57 signal, risk, or `TradeSetup`; consume the exact
  persisted decision payload.
- Do not select “latest” across dates, compatibility cohorts, or observations.
- Do not allow an order-book midpoint or another source to silently masquerade
  as the opening-price concept.
- Do not make `analyze` write a trade journal.
- Do not make `trade log` reread a live provider after the user inspected an
  immutable snapshot.
- Do not preserve `loop_intraday.sh` merely to call the removed command.

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

## 7. AI Usage Declaration

No AI involved.

## 8. Risk, Signal, and Evidence Authority

- The 08:57 persisted signal and `TradeSetup` remain unchanged and immutable.
- `ConfirmIntradayOpenUseCase` remains the sole post-open action policy.
- Pre-open output must be presented as the earlier directional/setup state;
  post-open `ENTER` / `WAIT` / `SKIP_*` is a later execution assessment.
- No post-open fact may flow backward into the pre-open observation or its
  compatibility identity.
- No diagnostic evidence is promoted and no tuning eligibility changes.

## 9. Data and Transport Contract

Single source of truth:

```text
learning_observations row
  + exact linked learning_track_snapshots row
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

Retire:

- `saham trade confirm`;
- `--track-file`, `--output`, live/manual price flags, and the old
  `--session PATH` sidecar meaning owned by the removed command; the new
  `--session YYYY-MM-DD` selector is a distinct database-session contract;
- confirmation sidecar loading/writing and “last confirmation” defaults;
- `loop_intraday.sh`;
- obsolete confirmation-sidecar tests, displays, factories, documentation, and
  cron references.

Do not delete unrelated historical trade journals.

## 10. Acceptance Criteria

- [ ] `saham analyze pre-open` is mounted under `analyze` and documented as a
      post-open assessment of an immutable pre-open plan.
- [ ] `saham trade confirm` and all its flags are absent from help and routing.
- [ ] `loop_intraday.sh` and mutable confirmation/session analysis sidecars are
      no longer production transport.
- [ ] The command reads the exact persisted pre-open observation and one linked
      immutable opening snapshot.
- [ ] Equivalent fixtures preserve existing post-open decision arithmetic.
- [ ] Pre-open direction/setup and post-open action are visibly distinct.
- [ ] `--format json` writes stdout only.
- [ ] Analysis performs no database, filesystem, journal, YAML, provider, or SDK
      I/O directly from the application layer.
- [ ] Explicit intraday trade logging consumes exact immutable IDs and cannot
      reread live state.
- [ ] Pre-open labels/evaluations remain unchanged.
- [ ] Documentation and CLI examples contain no removed route or sidecar path.

## 11. Testing Expectations

- Unit: exact observation/snapshot binding, unavailable opening state,
  compatibility ambiguity, and unchanged confirmation gates.
- Integration: persisted observation + linked track → typed analysis result.
- Producer-to-consumer: the exact snapshot ID shown by `analyze` is the one
  consumed by explicit trade logging; assert repository call counts.
- Negative CLI: removed command and every removed flag/path fail.
- Architecture: application imports no SQLite, filesystem, YAML, Typer, Rich,
  Stockbit SDK, or browser implementation.
- Regression: pre-open capture, track, labels, and evaluate suites remain green.
- All tests offline; run the full suite and `git diff --check`.

## 12. Documentation Impact

- Update CLI overview, intraday workflow, quick reference, building blocks,
  architecture index/ADR amendments, and cron/runbook references.
- Clearly state that `pre-open` names the originating strategy even though the
  analysis runs after 09:00.
- Document the three distinct artifacts:
  pre-open observation, post-open assessment, and later outcome label.

## 13. Delivery Sequence

1. Amend governing ADRs for command ownership and removal of sidecar transport.
2. Add typed application request/result and exact lineage tests.
3. Add repository-port reads and producer-to-consumer integration test.
4. Mount `saham analyze pre-open`.
5. Migrate explicit intraday trade logging to immutable IDs.
6. Remove `saham trade confirm`, sidecars, loop script, and compatibility tests.
7. Update documentation, run focused/full verification, and commit scoped files.

## 14. Agent Execution Instructions

Before implementation, read `AGENT_QUICKSTART.md`, `AGENTS.md`,
`TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`, ADR-026, ADR-033, ADR-048,
ADR-049, and the current executable CLI/application/repository paths.

State the semantic classification and exact transport design before editing.
If equivalent decision behavior cannot be proven, stop and request approval for
the required semantic contract change.

## Final Gate

The task is complete only when analysis is read-only and database-identified,
the old command and file transport are impossible, explicit journal writes use
the same immutable inputs, deterministic decisions are unchanged, focused and
full tests pass, and `git diff --check` is clean.
