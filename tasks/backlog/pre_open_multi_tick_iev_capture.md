# Task: Multi-Tick Pre-Open IEV Capture — Activate Locked-Input ΔIEV

Governing decision: [ADR-048](../../docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md)
(supplies `delta_iev` for the `auction_ncp` group)

Related: [ADR-047](../../docs/adr/ADR-047-scenario-adoption-seam-for-signal-risk-mce.md)

## 1. Task Metadata

**Task Title:** Add multiple `saham fetch iev` capture ticks across the pre-open
window so `delta_iev` / build-into-lock becomes computable and NCP-locked rows are
captured.

**Task Type:** Ops / scheduling (data capture).

**Priority:** **HIGH — perishable.** Pre-open auction state (IEV/IEP/book) is
**ephemeral and non-backfillable**: it exists only during the 08:45–09:00 window on
that specific morning and is not retrievable from any provider afterward. Every
trading day shipped without multi-tick capture is a **permanent hole** in a corpus
that can never be reconstructed. This is the reverse of swing/`research`, whose
inputs (candles) backfill on demand — so this task is urgent even though the
consuming signal (ADR-048) is not.

## 2. Problem Statement

The pre-open signal (ADR-048) wants `delta_iev` — how committed interest
strengthened or faded after the 08:56 lock and before 08:58 matching. The
persistence for the baseline is built:

* `SQLiteIEVRepository.save_snapshot` **appends a row to `iev_snapshot_history`**
  on every run.
* `get_locked_iev_baseline(date, before=...)` returns the earliest eligible
  [08:56, 08:58) row before final live collection.
* The application computes ΔIEV = final live candidate IEV − locked baseline.
* `is_ncp_locked` is stamped only inside [08:56, 08:58).
* `get_iev_delta(date)` remains an all-session diagnostic and is forbidden as
  production signal evidence.

**Status (ops):** `install_cron.sh` schedules diagnostic `fetch iev` ticks at
**08:47 / 08:50 / 08:53**, the locked baseline at **08:56**, and
`research pre-open capture` at **08:57**. Capture must finish before 08:58.
Remaining work: verify a live trading day and reinstall the host crontab with
`./install_cron.sh`.

## 3. Desired Outcome

* `saham fetch iev` captures a locked baseline at 08:56.
* `research pre-open capture` supplies the final live snapshot at 08:57 and
  finishes before 08:58 matching.
* Result: an overlapping ticker receives locked-input `delta_iev`; a ticker
  absent from the baseline remains MISSING, never fabricated.
* Pre-NCP ticks remain useful for diagnostics but cannot influence the signal.

Out of scope: signal/observation implementation (that is the
[pre-open signal task](pre_open_signal_evidence_and_observations.md)); any change to
the IEV writer schema.

## 4. Non-Goals (Explicitly Out of Scope)

* **No backfill of past dates** — impossible; pre-open auction state is forward-only.
  Do not attempt to reconstruct historical ΔIEV.
* No schema change to `SQLiteIEVRepository` / `iev_snapshot_history`.
* No signal scoring, no `auction_ncp` builder — those live in ADR-048's task.
* No promotion of `delta_iev` to a *required* field yet (ADR-048 keeps it optional
  until multi-snapshot capture is reliably landed — i.e. after this task).

## 5. Architecture Impact Assessment

* Layers touched:
  * Domain — exchange phase boundary and evidence contract.
  * Application — locked-baseline consumption and pre-matching provenance gate.
  * Infrastructure — time-filtered baseline query; no schema change.
  * Adapter / Ops — thin schedule and phase-label updates.
* Affects determinism? Yes: the same stored inputs reproduce the same locked
  delta, but pre-NCP/matching rows can no longer change production scoring.
* Persistence changes? No SQLite table migration; evidence and observation
  contracts create a new v3 cohort.
* Orchestration/policy inside an adapter? **No** — scheduling only.

```md
Layer plan:
- Domain: exact locked-input and matching boundaries
- Application: final-live-minus-locked-baseline delta and fail-closed timing
- Infrastructure: filtered locked-baseline reader
- Adapter: thin cron cadence and display labels
```

## 6. Implementation Notes & Considerations

* **Browser churn.** Each `saham fetch iev` boots a Playwright/Stockbit session.
  Keep ticks **≥ 2–3 minutes apart** so a slow run does not overlap the next. If
  session startup cost is high, prefer a **single pre-open loop** (see existing
  `loop_intraday.sh`) that reuses one session and captures at intervals, over N
  independent cron lines. Trade-off: cron-per-tick is simpler and crash-isolated;
  a loop is cleaner and lighter on session setup.
* **Locked-input baseline.** Capture at least one tick inside [08:56, 08:58).
  Decision write is separate and must finish before matching:
  `saham research pre-open capture`.
* **Exact boundary is architecture.** The baseline must be inside
  [08:56, 08:58), and the final decision must complete before 08:58.
* **JSON sidecar overwrites** (`data/iev/<date>/iev.json` keeps only the last tick).
  That is fine — `iev_snapshot_history` (SQLite) is the authority for delta/learning.
* **Laptop-asleep risk** — pre-existing for host cron on macOS; the earlier ticks
  are the same reliability bet as the current 08:55 tick.

## 7. Acceptance Criteria

* [ ] After a trading day, `iev_snapshot_history` holds **≥ 2 rows** for tickers
      present in multiple ticks.
* [ ] `get_locked_iev_baseline(today, before=capture_start)` returns a non-empty
      map for overlapping tickers.
* [ ] At least one captured row per day has `is_ncp_locked = 1`, stamped inside
      [08:56, 08:58) WIB.
* [ ] Authoritative capture completes before 08:58; a crossing run fails closed.
* [ ] `install_cron.sh` is idempotent and re-installs the multi-tick block cleanly
      (no duplicate/stale saham cron entries).
* [ ] No writer table/schema migration; existing and new IEV tests remain green.

## 8. Sequencing

This is a **prerequisite** for ADR-048's `delta_iev` to move from *optional* to a
*primary-when-present* `auction_ncp` input. It is independent of and **ahead of** the
pre-open signal task: it can (and should) ship first, because its data is perishable
while the signal design is not.

## Final Gate

Definition of Done: multi-tick capture live and idempotent; ΔIEV computable
forward from deploy day; no backfill claimed; no writer schema drift. If capture
cannot be made reliable (e.g. session/asleep issues), stop and report rather than
silently drop ticks.
