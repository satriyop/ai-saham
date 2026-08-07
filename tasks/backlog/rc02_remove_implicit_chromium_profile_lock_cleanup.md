# Remove Implicit Chromium Profile-Lock Cleanup

Status: `FIXED / VERIFIED` — implemented and vertically verified on 2026-08-07.

Source finding: RC-02 in
`tasks/backlog/review_code_2026-08-07.md` (`FIXED / VERIFIED` 2026-08-07).

## 1. Task Metadata

**Task Title**
Remove application-side Chromium profile-lock deletion from Stockbit reauth.

**Task Type**
Bugfix — infrastructure safety.

**Priority**
High. The current automatic reauth path can delete a concurrent browser's
ownership markers without proving ownership.

## 2. Problem Statement

`reauth_stockbit_session()` calls
`_clear_stale_chromium_profile_locks()` before both headless and headed
persistent-browser launch. The helper claims an unparseable marker is a no-op,
but malformed markers, read failures, and regular files leave `owner_pid=None`
and then delete the lock family.

Current executable counterexamples deleted every tested marker:

```text
malformed     lock_kept=False cookie_kept=False default_kept=False
foreign_dead  lock_kept=False cookie_kept=False default_kept=False
regular_file  lock_kept=False cookie_kept=False default_kept=False
```

Adding stricter parsing does not make the design safe. The check and deletion
are not atomic. A transient test replaced the checked dead lock with a new live
owner immediately before `ProcessLookupError`; the helper then deleted the new
live lock:

```text
replacement_live_lock_kept=False
```

The helper also deletes `RunningChromeVersion` and `Default/Lock`, which are not
part of the current POSIX `ProcessSingleton::Cleanup()` set. It swallows partial
unlink failures and proceeds to browser launch with potentially inconsistent
marker state.

## 3. Current External Authority Evidence

Chromium owns the user-data-directory singleton protocol. Its current POSIX
implementation creates `SingletonLock` as a hostname/PID symlink, uses matching
socket/cookie links, handles invalid/stale locks, checks browser-process
identity, and owns cleanup. See Chromium's
[`process_singleton_posix.cc`](https://chromium.googlesource.com/chromium/src.git/+/refs/tags/146.0.7680.21/chrome/browser/process_singleton_posix.cc)
and
[`process_singleton_lock_posix.cc`](https://chromium.googlesource.com/chromium/src/+/master/chrome/common/process_singleton_lock_posix.cc).

An executable probe against the installed Playwright 1.58 full Chromium binary
and temporary profiles confirmed:

```text
first owner: SingletonLock -> pamungkas.local-14851
second launch: rejected with "Failed to create a ProcessSingleton ... profile
               is already in use"
lock after rejected second launch: unchanged
lock after owner close: removed

dead local stale lock: Chromium launch succeeded and installed its own lock
malformed stale lock: Chromium launch succeeded and installed its own lock
both locks after owner close: removed
```

The default Playwright headless-shell binary did not create a `SingletonLock`
and admitted a second temporary-profile context in the probe. This is further
reason not to invent one application policy across different browser binaries.
Whichever installed Chromium variant is launched remains the sole ownership
arbiter.

## 4. Desired Outcome

- Stockbit reauth performs no pre-launch deletion, rewrite, repair, parsing, or
  liveness decision for Chromium profile ownership markers.
- Chromium/Playwright exclusively decides whether the profile is available,
  stale, invalid, or concurrently owned.
- A concurrent-owner launch failure propagates through the existing
  infrastructure exception boundary; the CLI continues to print
  `Reauth failed: <upstream reason>` and exit non-zero.
- Headless and headed reauth retain their current JWT/session behavior when
  browser launch succeeds.
- No Signal, Risk, TradeSetup, Action, evidence, corpus, or configuration
  identity changes.

## 5. Exact Implementation

In `src/infrastructure/browser/stockbit_session_actions.py`:

1. Delete `_clear_stale_chromium_profile_locks()` completely, including its
   stale docstring.
2. Delete its unconditional call from `reauth_stockbit_session()`.
3. Do not replace it with another parser, PID probe, hostname comparison,
   filesystem-type check, lock preflight, retry, or automatic unlink path.
4. Keep `_persistent_context()` as the one browser launch boundary and retain
   existing exception propagation.

In `tests/infrastructure/browser/test_stockbit_reauth_modes.py`:

1. Remove tests that assert application deletion of dead Chromium markers.
2. Add parameterized preservation tests for malformed, empty, numeric-dead,
   foreign-host, regular-file, symlink, and unexpected-directory markers.
3. At the `_persistent_context` seam, assert every marker is still byte/type/
   link-target identical when launch begins.
4. Make the fake launch raise a sentinel profile-in-use error and assert reauth
   propagates it without any filesystem change.

In `tests/adapters/cli/test_fetch_stockbit_commands.py`:

- Assert a propagated profile-in-use exception produces exit code 1 and the
  existing `Reauth failed:` error boundary without leaking credentials or
  tokens.

No new command, configuration option, retry policy, or exception-string parser
is required.

## 6. Non-Goals / Do Not Interpret This As

- No automatic or explicit `unlock-profile` command.
- No PID killing, process-name lookup, hostname normalization, or NFS policy.
- No retry after a profile-in-use error.
- No attempt to duplicate Chromium's singleton parser or cleanup algorithm.
- No deletion of `SingletonLock`, `SingletonCookie`, `SingletonSocket`,
  `RunningChromeVersion`, `Default/Lock`, or any profile object.
- No change to browser profile location, login, reauth mode defaults, JWT
  validation, token persistence, or cron configuration.
- No broad catch that converts unrelated browser-launch failures into a
  profile-lock diagnosis.
- No domain/application policy or adapter-owned recovery workflow.

If future operational evidence proves the installed browser cannot recover a
genuinely stale profile, that is a new explicit recovery-design task. It must
not restore implicit deletion to reauth.

## 7. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: remove unsafe pre-launch mutation from Stockbit session actions
- Adapter: behavior unchanged; add an error-boundary regression test only
```

- New dependency: No.
- Determinism: Improved operationally; browser ownership remains with the
  browser implementation rather than a racing approximation.
- Persistence change: No schema or business-data change. Browser-owned profile
  files are no longer mutated by ai-saham before launch.
- Warm-up data: No.
- Adapter policy: No. The CLI only maps an exception to error output and exit 1.

Semantic classification: `NON_SEMANTIC` for canonical market-analysis identity.
This intentionally changes infrastructure recovery behavior but cannot change
Action compatibility, evidence meaning, observation schema, or labels.

## 8. AI Usage Declaration

No AI involved. The behavior is deterministic infrastructure and upstream
browser ownership.

## 9. Risk, Signal, And Evidence Authority

- SignalEngine: unchanged.
- RiskEngine: unchanged.
- TradeSetup/Action: unchanged.
- Market context and evidence authority: unchanged.
- Tuning/promotion: unchanged.

The safety impact is limited to persistent-browser session integrity. Failure
to launch produces no token refresh; it does not create a fallback data or
decision path.

## 10. Data And Persistence

The Stockbit Chromium user-data directory is read and written by the launched
browser as before. ai-saham must not directly write or delete its singleton
ownership objects during reauth. `token.json` and `.logged_in_at` retain their
current successful-auth-only behavior.

No SQLite, schema, config, migration, corpus, artifact, or business-persistence
change is permitted.

## 11. Failure-State Contract

| State | Required result |
|---|---|
| No ownership marker | launch normally |
| Valid live owner | Chromium rejects or handles according to its protocol; ai-saham performs zero mutation and surfaces failure |
| Dead local marker | Chromium handles it; ai-saham performs zero pre-launch mutation |
| Malformed/empty/regular/directory marker | Chromium handles or rejects it; ai-saham performs zero mutation |
| Foreign-host/shared profile | Chromium platform behavior is authoritative; ai-saham does not reinterpret it |
| Permission/read error | browser launch error propagates; no cleanup retry |
| Partial or unrelated launch failure | original failure propagates; no lock diagnosis inferred and no marker changed |

## 12. Acceptance Criteria

- [x] `_clear_stale_chromium_profile_locks` and every call/reference are absent.
- [x] Reauth reaches `_persistent_context` without directly touching any lock
      family path.
- [x] Every adversarial marker remains identical before the mocked launch.
- [x] Concurrent/profile-in-use errors remain non-zero and actionable through
      the existing CLI boundary.
- [x] Headless and headed success behavior remains covered.
- [x] No unlock/retry/fallback path is introduced.
- [x] No product persistence, config, or semantic identity changes.
- [x] Focused tests, full required suite, Ruff check/format, and
      `git diff --check` pass on the final state.

## 13. Testing Expectations

Focused minimum:

```text
tests/infrastructure/browser/test_stockbit_reauth_modes.py
tests/infrastructure/browser/test_playwright_stockbit_session_management.py
tests/adapters/cli/test_fetch_stockbit_commands.py
```

All tests run offline with temporary paths and fake Playwright seams. Do not
make full-browser availability a CI requirement. The local full-Chromium probes
above are vet evidence, not a portable test dependency.

Because implementation touches Python, close with:

```text
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
.venv/bin/python -m pytest -q --basetemp=<bounded-temp-path>
git diff --check
```

## 14. Documentation Impact

- README update: No; no public command changes.
- New config option: No.
- Limitation: a profile Chromium cannot safely acquire requires the operator to
  close the owning browser or investigate externally; reauth will not delete
  ownership markers.

## 15. Agent Execution Instructions

Before implementation, re-read `AGENT_QUICKSTART.md`, `AGENTS.md`,
`DEFINITION_OF_DONE.md`, and the relevant infrastructure/testing sections of
`PROMPT_CONTRACT.md` and `AI_AGENT_CHECKLIST.md`. Confirm the exact shared
worktree state and preserve unrelated staged/unstaged changes. Implement only
the deletion removal and tests above; stop if another feature appears to depend
on automatic lock deletion.

The implementation is complete only when the exact final state proves zero
application-side lock mutation and all close gates pass.

## 16. Implemented Result And Verification

Implemented exactly as designed:

- deleted `_clear_stale_chromium_profile_locks()` and its unconditional call;
- added six adversarial marker-shape tests that prove the complete marker
  family remains identical at launch and after a launch failure;
- added a CLI profile-in-use regression proving exit 1, actionable existing
  error projection, and no token leakage;
- added no replacement parser, PID/hostname check, retry, unlock command, or
  filesystem mutation.

Final verification on 2026-08-07:

```text
focused Stockbit infrastructure/CLI tests: 50 passed
whole-repository Ruff check: passed
whole-repository Ruff format check: 1769 files already formatted
full pytest: 6641 passed, 41 skipped
production grep: cleanup helper and os.kill probe absent
git diff --check: passed
```

The full-Chromium temporary-profile probes from the vet remain characterization
evidence only; the automated suite is offline and does not require a browser.
Unrelated staged and unstaged worktree changes were preserved.
