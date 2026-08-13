# Task — Pre-open lane pre-flight: fail loudly at 08:41, not silently at 19:30

## 1. Task Metadata

**Task Type:** Feature
**Priority:** High — the protected lane is the only unrecoverable one in the system.
**Opened:** 2026-08-13

---

## 2. Problem Statement

The pre-open lane captures the IDX NCP lock window (08:56–08:58 WIB). That
capture exists only inside the lock window: unlike the accum corpus, it **cannot
be replayed**. `saham research accum signal-backfill-observations` has no
pre-open equivalent, and never can — the input phase is gone by 09:00.

Today nothing tells the operator that the lane is broken until the corpus
continuity watchdog runs at **19:30**, eleven hours after the window closed. By
then the only available action is to record that the day is lost.

This is not hypothetical. Measured:

- `iev_snapshots` jumps **2026-08-06 → 2026-08-10**. Session **2026-08-07 is
  absent** and is permanently unrecoverable.
- The cause is in `logs/iev-collector.log`:
  ```
  Fetching IEV snapshot (top 50 movers)...
  Token refresh did not return a usable RS256 Exodus JWT
  No movers returned — session may be expired.
  ```
- The IEV collector's own coverage line measures the ongoing rate:
  `recent 13/14 days (93%) had a lock-window batch` — a ~7% loss rate on an
  unrecoverable lane.

Three things make the failure silent rather than loud:

1. The 08:40 reauth cron entry ends in `|| true`, so a failed reauth is
   indistinguishable from a successful one at the cron level.
2. `saham fetch iev` prints `No movers returned` and exits **0**.
3. `saham fetch stockbit status` renders token health for humans but has no
   exit-code contract, so no script can act on it.

The diagnosis already exists in the logs. What is missing is anything that reads
it **before 08:56**, while there is still time to run
`saham fetch stockbit reauth --mode headed` by hand.

---

## 3. Desired Outcome

Two alarms inside the recovery window, each with a stated margin:

```
08:40  reauth headless
08:41  PRE-FLIGHT   token state + horizon      → alarm, 15 min margin
08:47  fetch iev
08:48  VERIFY       rows stored for today?     → alarm,  8 min margin
08:56  fetch iev    ← NCP lock window
08:57  pre-open capture
```

- **Pre-flight (08:41)** answers: *will the session still be usable at the NCP
  window?* Not "is the token valid now" — a token valid at 08:41 but expiring at
  08:50 is a failure this check must catch. Note the measured TTL is exactly 24h
  from each 08:40 reauth (token seen expiring `08:40:11` the following day), so
  a failed reauth leaves a token expiring *during* the pre-open lane.
- **Verify (08:48)** answers: *did the 08:47 fetch actually store data?* This is
  the live proof the local token check cannot give (`StockbitSessionStatus`
  docstring: local validity "does not prove Stockbit has accepted the token").
  It costs no extra API call — it reads what the already-scheduled fetch wrote.

Observable change: a broken pre-open lane produces a macOS notification and a
non-zero exit at 08:41 and/or 08:48, with the remediation command in the message.

**Out of scope for this task** — see §4.

---

## 4. Non-Goals (Explicitly Out of Scope)

- **No auto-recovery.** The remediation is `reauth --mode headed`, which needs a
  UI; headless recovery is precisely what already fails. This task alarms, it
  does not self-heal.
- No new data provider, no extra API call, no change to what `fetch iev` or
  `research pre-open capture` do.
- No change to reauth logic itself (hardened separately in `1fe8aa12`).
- No risk/signal/evidence-authority policy change; nothing here touches scoring
  or cohort identity.
- No change to the accum lane or to the 19:30 continuity watchdog.

---

## 5. Architecture Impact Assessment

**Layers touched:**

- **Domain** — one narrow port. `iev_snapshots` currently has *no* port;
  `SQLiteIEVRepository` is concrete infrastructure, and application may not
  import it (`tests/architecture/test_layer_boundaries.py`).
  Add `PreOpenIevSnapshotCountPort` (count rows for one session date).
- **Application** — `AssessPreOpenLaneReadinessUseCase` + DTOs. All policy lives
  here: what "still usable at the NCP window" means, how much margin is
  required, when the fetch check becomes due, and whether a non-trading day
  suppresses the alarm.
- **Infrastructure** — one method, `SQLiteIEVRepository.count_snapshot_rows`.
- **Adapter** — thin CLI command + cron wrapper script. Parses flags, calls the
  use case, formats output, maps to exit codes. Owns no policy.

**New dependency:** No.

**Why the adapter stays thin:** the adapter must not decide whether the lane is
healthy. "Is a token with N seconds remaining sufficient for a window that ends
at 08:58" and "is the fetch check due yet" are business-status calculations,
which `CLAUDE.md` places in application. The CLI passes clock and config in and
maps a verdict to an exit code out.

**Holiday suppression:** the cron fires Mon–Fri, but IDX holidays are not
trading sessions. A false alarm on a holiday trains the operator to ignore the
alarm, which defeats the whole task. Reuse
`TradingSessionCalendarSnapshotReadRepository` — the same attested-calendar port
the continuity watchdog uses. Absent calendar authority must **not** silently
suppress; report it distinctly, as `NO_CALENDAR_AUTHORITY` does in
`audit_corpus_continuity_use_case`.

---

## 6. Exit-code contract (mirrors the continuity watchdog)

| Code | Meaning |
|---|---|
| 0 | lane on track (or not due / not a trading session) |
| 1 | lane at risk — notify, remediation still possible |
| 2 | broken environment — venv missing, `saham` absent, DB unreadable |

Distinguishing 1 from 2 matters: a broken checker must never be reported as a
healthy lane.

---

## 7. Verification

- Unit tests for the use case: token valid-but-expiring-inside-window, token
  expired, fetch check not-yet-due vs due-and-empty, holiday suppression,
  missing calendar authority, and the boundary where margin exactly equals the
  requirement.
- CLI tests: exit codes 0/1/2, `--format json`, explicit `--db` failing closed.
- Cron script exercised in all three exit paths under a minimal `env -i`
  environment, as the continuity watchdog was.
- Lint Gate: `ruff check src/ tests/` and `ruff format --check src/ tests/`.

---

## 8. Sequencing note

The 08:48 verify check subsumes what a live token probe would prove, so no live
probe is added. If the verify check ever needs to run before any fetch has been
scheduled, revisit that decision — do not add an API call to the 08:41 slot
without one.
