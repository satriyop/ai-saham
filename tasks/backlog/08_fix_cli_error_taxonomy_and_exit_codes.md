# CLI Error Taxonomy, Honest Empty States, And Exit Codes

Status: `READY` — independent; ships anytime.
Sequence: **8 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Give the CLI one error taxonomy so users can tell "nothing found" from "your
install is broken."

**Task Type**
Bugfix (adapter)

**Priority**
Medium — low engine risk, high trust impact.

---

## 2. Problem Statement

There is no error-mapping layer. Every command does its own local
`try/except` → `typer.echo(..., err=True)`.

Verified counts across `src/adapters/cli/*.py` (2026-08-04 — use these, an
earlier draft of this task said "63" and was wrong):

| pattern | count |
|---|---|
| `typer.echo(f"Error` | **38** |
| any `typer.echo(..."Error` | **50** |
| any `err=True` call | **250** |
| files containing `err=True` | **57** |

Confirmed samples: `fetch_market_commands.py:148` and
`fetch_financials_commands.py:128` are both bare `typer.echo(f"Error: {e}", err=True)`;
`backtest_portfolio_runner.py:116` is `typer.echo(f"Error: invalid date format: {e}", err=True)`.
A handful add red styling (`fetch_broker_error_display.py:20-52`); most print the
raw exception.

**Scope note:** the 38 bare-`Error:` sites are the clear migration target. The
gap between 50 and 250 is other stderr output (warnings, hints, progress) that is
**not** in scope — slice 2 must triage, not blanket-convert. Establish the real
denominator in slice 1 before touching call sites.

The consequence is that failures are indistinguishable from empty results.
Live-tested on 2026-08-04:

| Input | Actual behavior |
|---|---|
| `screen accum ZZZZ` | exit **0**, `No candidates found…`, plus a leaked internal warning: `⚠ Market context unavailable (display-only): Universe '1 tickers' not found. Available: bank, basic_materials, …` |
| `view BOGUSTICKER` | exit **0**, full dashboard of empty panels, `not fetched — run: saham fetch market BOGUSTICKER` |
| `--db /nonexistent.db` | silently **creates** a new empty SQLite file |
| `screen accum` (no candidates) | exit **0** — same code as success |
| `view ticker show --db …` | `No such option: --db`, though sibling commands accept it |

Two further defects on the command users are told to run first:

- `saham fetch status` resolves `data.db` rather than the configured
  `data/db/data.db` (`tasks/thought/improvement_saham_screen.md:628-640`), so it
  can report "no database" while the rest of the app reads real data.
- The same document notes it reported Yahoo as healthy despite a logged DNS failure.

`CLI_TROUBLESHOOTING.md` documents a clean set of messages
(`Error: No cached data found for BBCA` + a `Tip:` line, `Error: Database not
found at …`, `Error: Network connection failed.`) — but several of these are
**aspirational**: the `--db` case demonstrably creates a file instead.

Additionally, `saham today` truncates warnings to five rows, which can hide
BLOCKER-level warnings entirely (`tasks/thought/improvement_saham_today.md:391`),
and Rich markup like `[local_clock]` is interpolated and silently vanishes from
output (line 410).

---

## 3. Desired Outcome

- One error taxonomy shared by all commands, with distinct categories at
  minimum: bad input, missing data, missing/unreadable database, provider or
  network failure, and internal error.
- Distinct exit codes: success, valid-empty result, user error, data
  unavailable, internal error.
- A bad ticker produces a clear bad-ticker message, not "no candidates."
- A nonexistent `--db` path errors; it never silently creates a database.
- `fetch status` reads the configured DB path and reports provider health honestly.
- Critical warnings are never hidden by truncation.
- Documented messages in `CLI_TROUBLESHOOTING.md` match reality — verified by test.

---

## 4. Non-Goals

- **No engine, scoring, or gate changes.**
- No change to what any command computes.
- No new commands. (A `doctor` command is tempting; `fetch status` already
  occupies that role — fix it rather than adding a rival.)
- No flag renames beyond adding `--db` where its absence is an inconsistency.
- No output restructure (task 7 owns that).

---

## 5. Architecture Impact Assessment

- **Domain:** not touched.
- **Application:** error categories may need typed application-level exceptions
  so adapters can map without inferring. Introduce only if adapters cannot map
  cleanly from existing types — do not push presentation concerns down.
- **Infrastructure:** DB open path must not create-on-missing when the caller
  supplied an explicit path.
- **Adapter:** the taxonomy, the mapping, the exit codes, the copy.

New dependency: **No.**
Determinism: **No.**
Persistence: **Behavioral** — stop implicitly creating databases. Verify no
legitimate first-run flow depends on create-on-missing; if one does, make it
explicit (`--init`) rather than silent.
Warm-up: **No.**
Policy in adapter: **No.** Error *mapping* is adapter work; deciding whether
data is stale or must be fetched is not, and stays in application.

```md
Layer plan:
- Domain: not touched
- Application: typed error categories only if adapters cannot map existing
  exceptions cleanly; no workflow change
- Infrastructure: explicit-path DB open must not create; honest provider probes
  in the status path
- Adapter: single error-mapping module, exit codes, message copy, --db parity
```

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority Considerations

No decision component changes. **Does this change what can produce
ENTER/WATCH/AVOID? No.**

One safety-relevant item: warning truncation currently able to hide BLOCKER-level
warnings is a genuine risk-communication defect. Severity-ordered display with
critical warnings never truncated is required, not optional.

---

## 8. Data & Persistence

- **Read:** config-resolved DB path; provider health probes.
- **Written:** nothing new. **Stops** writing a new SQLite file on a bad `--db`.
- **Schema change:** No.
- **Semantic equivalence:** `fetch status` changing which DB it reads is a
  source change. Confirm the configured path (`config/default.yaml:31`) is the
  correct authority and that no workflow depends on the old `data.db` default.

---

## 9. Acceptance Criteria

- [ ] One error-mapping module; the 38 bare `Error: {e}` sites replaced, and the
      triage decision for the remaining stderr output recorded.
- [ ] Documented exit codes; success and valid-empty are distinct.
- [ ] Bad ticker → clear message, non-zero exit, no internal leak.
- [ ] Nonexistent explicit `--db` → error, no file created.
- [ ] `fetch status` reads the configured path; provider health reflects reality.
- [ ] Critical warnings never truncated; severity-ordered.
- [ ] Rich markup in dynamic strings escaped, not silently interpolated.
- [ ] `--db` accepted consistently, or its absence documented as deliberate.
- [ ] Every message in `CLI_TROUBLESHOOTING.md` verified by test.
- [ ] **Lint Gate** passes.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Taxonomy and exit codes.**
Error category enum, mapping module, exit-code constants, tests. No call sites
migrated yet.
Commit: `feat(cli): add error taxonomy and exit code contract`

**Slice 2 — Migrate call sites.**
Replace the 38 bare `Error:` handlers. Triage the remaining `err=True` output
(warnings/hints/progress) explicitly — do **not** blanket-convert all 250.
Record which were converted and which were deliberately left.
Commit: `refactor(cli): route command errors through the shared taxonomy`

**Slice 3 — Honest empty and bad-input states.**
Bad ticker, valid-empty, and the leaked `Universe '1 tickers' not found` warning.
Commit: `fix(cli): distinguish bad input from valid-empty results`

**Slice 4 — Database path honesty.**
Explicit `--db` never creates. `fetch status` reads the configured path. `--db`
parity across commands.
Commit: `fix(cli): stop silently creating databases and fix status db path`

**Slice 5 — Warning severity and markup escaping.**
Severity ordering, no truncation of critical warnings, escape dynamic markup.
Commit: `fix(cli): never truncate critical warnings; escape dynamic markup`

**Slice 6 — Documentation truth.**
Reconcile `CLI_TROUBLESHOOTING.md` with actual behavior; add verifying tests.
Commit: `docs(cli): align troubleshooting guide with verified behavior`

---

## 11. Testing Expectations

- Each error category maps to its documented exit code.
- Bad ticker, empty result, missing DB, unreadable DB, provider failure — each
  produces its own category and code.
- Nonexistent `--db` creates no file (assert filesystem state).
- Critical warning survives with more than five warnings present.
- Dynamic strings containing `[` render literally.
- Doc-truth test: every `Error:` string in `CLI_TROUBLESHOOTING.md` is produced
  by some code path.

Note the known hazard from `test_suite_fast_loop`: CLI invoke tests can leak
live network. Stub providers explicitly. Offline. Ruff before close.

---

## 12. Documentation Impact

- README: **No.**
- `CLI_TROUBLESHOOTING.md`: **Yes** (slice 6).
- `CLI_REFERENCE.md`: **Yes** — document exit codes.
- New config options: **No.**
- Limitations: **No.**

---

## 13. Required Reading

- `AGENT_QUICKSTART.md` — adapter thinness rules
- `CLI_TROUBLESHOOTING.md`
- `tasks/thought/improvement_saham_screen.md` §"UI/UX review", lines 628-640
- `tasks/thought/improvement_saham_today.md` lines 365-410

---

## 14. Do Not Interpret This As

- **Not** permission to move fetch/cache/freshness decisions into the adapter.
  Mapping an error is adapter work; deciding to fetch is not.
- **Not** permission to suppress warnings to make output tidy.
- **Not** permission to change any computed value.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Exit code table:
- Ad-hoc handlers replaced (count):
- Test / Lint result:
