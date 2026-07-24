# Task: Effective-session transparency + `--as-of` for `screen accum` and `analyze swing`

## 1. Task Metadata

- **Task Title:** Surface the effective session and add `--as-of` to `screen accum` and `analyze swing`
- **Task Type:** Feature (adapter-thin + one application threading change)
- **Priority:** Medium

## 2. Problem Statement

`screen accum` and `analyze swing` silently resolve **different effective market
sessions** for the same ticker on the same calendar day:

- `screen accum` anchors to the **last settled session** (e.g. 2026-07-23).
- `analyze swing` uses the **live snapshot** (e.g. 2026-07-24, `is_eod_pending=True`).

This is *correct behavior per purpose* (discovery/corpus must be reproducible;
a live entry decision wants the freshest price) — but it is **invisible**. A user
sees two different `accum_score` / `flow_confirmation_group` values for "BBRI
today" with no explanation. This reads as a bug and cost this team a multi-turn
investigation to untangle. The divergence is entirely explained by the effective
session: pinned to the same session, the flow group is byte-identical
(proven: 39.46 across reruns).

## 3. Desired Outcome

1. Both commands **display the effective session** they resolved, in table and
   JSON output — e.g. `Effective session: 2026-07-23 (settled)` vs
   `Effective session: 2026-07-24 (live · EOD pending)`.
2. Both commands accept **`--as-of YYYY-MM-DD`** that pins the effective session,
   defaulting to current behavior when omitted.
3. When both commands are pinned to the same `--as-of`, `accum_score` and
   `flow_confirmation_group` are **identical** for the same ticker/window.
4. **One as-of vocabulary across the CLI.** All point-in-time commands use the
   flag name `--as-of`, matching the `as_of_date` identifier used throughout the
   code. This includes renaming the existing `analyze signal inspect --date` to
   `--as-of` as a **clean break** (see §6a) — no deprecated alias.

## 4. Non-Goals (Explicitly Out of Scope)

- Do **not** unify the two default as-of policies. `screen accum` stays settled;
  `analyze swing` stays live. Only make the resolved session **visible and
  overridable**. Forcing them equal would break either corpus reproducibility or
  live-entry freshness.
- No new providers, no scoring/formula changes, no persistence schema changes
  (the corpus already stores `data_as_of_date`, `is_eod_pending`, etc.).
- Do not change `research signal capture` (already pins via `--session`).

## 5. Layer Plan

- **Domain:** not touched.
- **Application:** thread an optional `as_of` into the two workflow use cases so
  it feeds the effective-session resolution. This is the only non-adapter change.
  - `run_accumulation_screen_workflow_use_case.py` currently hardcodes
    `run_at=datetime.now(IDX_TIMEZONE)` (line ~141). Accept an optional pinned
    `as_of_date` on the request/method and, when present, build `run_at`
    deterministically (`datetime.combine(as_of, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)`)
    so the resolver returns that settled session. Keep `now` as the default.
  - `swing_analysis_input_collector.py` (lines ~103-107) already derives
    `run_at` from `request.today` (settled) vs `datetime.now` (live). Swing's CLI
    already computes `today = date.today()` (`analyze_swing_commands.py:252`) and
    passes it as `request.today`. So swing needs **only** to let `--as-of`
    override `today`; the collector logic is already correct.
- **Infrastructure:** not touched. `EffectiveMarketSessionResolver.resolve`
  already supports the needed control via `run_at`/`decision_at`; no change.
- **Adapter:** add the `--as-of` option to both CLIs, parse/validate it, thread it
  into the request, and render the effective-session line in table + JSON output.

Adapters remain thin: they parse a date, pass it down, and format the resolved
`EffectiveMarketSession` the application already returns. No as-of *policy* lives
in the adapter — the resolver still owns weekend/pre-close/after-close logic.

## 6. Reference Implementation (COPY THIS PATTERN)

`src/adapters/cli/analyze_signal_inspect_commands.py` **already implements this
exact feature** and is the canonical pattern to follow:

- Option: `as_of_date` / `--date`, help `"Point-in-time as-of date YYYY-MM-DD
  (defaults to today)."` (lines ~45-49)
- Parse + validate with `date.fromisoformat`, fail-closed on bad input
  (lines ~72-77)
- Wire `EffectiveMarketSessionResolver` and pass `as_of_date=day` (lines ~100-104)
- Render: `typer.echo(f"As-of: ...")` and `"Effective session: ..."`
  (lines ~125-129)

Name the flag **`--as-of`** (not `--date`) for the two new commands, but mirror the
parsing/validation/render structure verbatim.

### 6a. Clean-break rename of the reference command

`analyze signal inspect` currently exposes the flag as **`--date`** while its own
variable is `as_of_date` — an existing inconsistency. As part of this task, rename
that flag to **`--as-of`** outright (**clean break — do NOT keep `--date` as a
hidden/deprecated alias**; a lingering second name for one concept is exactly the
confusion we are removing). Update its help text, any docs/examples, and tests
that invoke `--date`. This is consistent with the repo's clean-break convention
(cf. the `research` corpus remount). After this task, `--as-of` is the single
point-in-time flag across `screen accum`, `analyze swing`, and
`analyze signal inspect`.

## 7. Implementation Steps

1. **screen accum adapter** (`screen_accum_commands.py`): add
   `--as-of YYYY-MM-DD` option; parse/validate; thread into the screen request /
   `RunAccumulationScreenWorkflowUseCase` path.
2. **screen accum application**
   (`run_accumulation_screen_workflow_use_case.py:~140`): when a pinned as-of is
   present, pass `run_at=datetime.combine(as_of, MARKET_CLOSE, IDX_TIMEZONE)` into
   `self._live_signal_evidence_context_uc.execute(run_at=...)`; else keep
   `datetime.now(IDX_TIMEZONE)`. Ensure `request.as_of_date` and the
   execution-context session stay consistent (both derived from the same pinned
   date) — see codebase-known-pitfalls "thread as_of_date through a service".
3. **analyze swing adapter** (`analyze_swing_commands.py:252`): add `--as-of`;
   when present, use it instead of `date.today()` for `today` (which already
   flows to `request.today` → settled resolution in the input collector).
4. **Render the effective session** in both commands' human + JSON output. Pull
   from the resolved `EffectiveMarketSession` (`analysis_as_of` /
   `latest_completed_session` / `market_session_name` / `is_eod_pending`). Surface
   it in the existing display/formatter modules (e.g. screen_accum single/multi
   displays; `analyze_swing_overview_display.py`) and add the field(s) to the
   JSON contract.
5. Keep the JSON `schema_version` / contract additions backward-compatible
   (additive fields only).
6. **Rename `analyze signal inspect --date` → `--as-of`** (clean break, no alias;
   see §6a). Grep for `--date` usages tied to inspect across `src/adapters/cli/`,
   `docs/`, `CLI_README.md`, and `tests/` and update every one. Confirm no other
   command relies on that flag name.

## 8. Test Specification

Add an application/adapter test (see `tests/adapters/cli/`) that:

1. Runs the shared accumulation `screen_use_case` **and** the swing path (or its
   candidate builder) for the same ticker pinned to the same `--as-of` date and
   asserts `accum_score` and `flow_confirmation_group` are **equal**.
   - Harness shape (verified working this session): build the execution context
     via `create_live_signal_evidence_execution_context_use_case(market_repo)`,
     call `.execute(run_at=<tz-aware WIB datetime>)`, pass the returned
     `execution_context` into `screen_use_case.execute(request, execution_context=...)`,
     then read the flow group from
     `candidate.signal_assessment.assessment.to_dict()["breakdown"]["flow_confirmation_group"]`.
     `run_at` MUST be timezone-aware (WIB / `IDX_TIMEZONE`) or the resolver raises.
2. Asserts determinism: same pinned as-of run twice → identical flow group.
3. Asserts the resolved effective session appears in each command's output
   (table line and JSON field), and that `is_eod_pending` is `True` for a live
   (intraday) run and `False`/absent for a settled pinned date.
4. Asserts `--as-of` with an invalid string fails closed with a clear error
   (mirror the inspect command's validation test if one exists).

Follow CLAUDE.md testing rules: use Opus to reason edge cases, Sonnet subagent to
write tests, run tests in a subagent to avoid context pollution.

## 9. Definition of Done

- [x] `--as-of` works on both commands; default behavior unchanged when omitted.
- [x] Effective session rendered in table + JSON for both commands.
- [x] Pinned to the same as-of, both commands report identical `accum_score` and
      `flow_confirmation_group` for the same ticker/window (test proves it).
- [x] No scoring/formula/schema-breaking changes; JSON additions are additive.
- [x] Adapters remain thin; as-of *resolution policy* stays in the resolver.
- [x] `analyze signal inspect` flag renamed `--date` → `--as-of` (clean break, no
      alias); all docs/examples/tests updated; no stray `--date` references remain.
- [x] `--as-of` is the single point-in-time flag across `screen accum`,
      `analyze swing`, and `analyze signal inspect`.
- [x] Tests pass; `AGENT_QUICKSTART.md` layer-plan compliance stated in the PR.

## 10. Key Anchors (verified this session)

| Concern | Location |
|---|---|
| Reference implementation | `src/adapters/cli/analyze_signal_inspect_commands.py` (~45-129) |
| Effective session resolver | `src/application/services/effective_market_session_resolver.py` (`resolve(run_at=, decision_at=)`; supports pinning) |
| Screen run_at injection (hardcoded `now`) | `src/application/use_case/run_accumulation_screen_workflow_use_case.py:~141` |
| Live execution-context factory | `src/adapters/cli/screen_accum_workflow_factory.py:169` (`create_live_signal_evidence_execution_context_use_case`) |
| Swing run_at from `request.today` (already settled-capable) | `src/application/services/swing_analysis_input_collector.py:~103-107` |
| Swing CLI `today = date.today()` | `src/adapters/cli/analyze_swing_commands.py:252` |
| Effective session fields | `EffectiveMarketSession`: `analysis_as_of`, `latest_completed_session`, `market_session_name`, `is_eod_pending`, `resolution_source` |
