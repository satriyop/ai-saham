# Task: Multi-Tick Pre-Open IEV Capture (08:47 → NCP) — Activate the ΔIEV Path

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

The pre-open signal (ADR-048) wants `delta_iev` — how interest **strengthened or
faded into the NCP lock** — as a primary `auction_ncp` input. The persistence for
this is **already built**:

* `SQLiteIEVRepository.save_snapshot` **appends a row to `iev_snapshot_history`**
  on every run.
* `get_iev_delta(date)` already computes ΔIEV = `last_iev − first_iev` per ticker,
  requiring **≥ 2 history rows** for that ticker that day.
* `is_ncp_locked` is stamped from the capture time (rows inside [08:56, 09:00) = 1).

**Status (ops):** `install_cron.sh` now schedules multi-tick `fetch iev` at
**08:47 / 08:50 / 08:53 / 08:57** and `research pre-open capture` at **08:58**.
Remaining work: verify a live trading day (ΔIEV non-empty, `is_ncp_locked=1`) and
retire any stale single-tick host crontab by re-running `./install_cron.sh`.

## 3. Desired Outcome

* `saham fetch iev` runs at **several timestamps across the pre-open window**, e.g.
  **08:47, 08:50, 08:53** (pre-NCP) **plus one NCP-locked tick ~08:57** (inside
  [08:56, 09:00)).
* Result: ≥ 2 same-day `iev_snapshot_history` rows for overlapping tickers →
  `get_iev_delta` non-empty; at least one row per day has `is_ncp_locked = 1`.
* `delta_iev` is thereby available (going forward only) to feed ADR-048's
  `auction_ncp` group as a **MISSING-safe** input (a ticker with < 2 rows that day
  simply has no delta → treated as MISSING, never fabricated).

Out of scope: signal/observation implementation (that is the
[pre-open signal task](pre_open_signal_evidence_and_observations.md)); any change to
the IEV writer schema.

## 4. Non-Goals (Explicitly Out of Scope)

* **No backfill of past dates** — impossible; pre-open auction state is forward-only.
  Do not attempt to reconstruct historical ΔIEV.
* No change to `SQLiteIEVRepository` / `iev_snapshot_history` schema or the append
  logic (already correct).
* No signal scoring, no `auction_ncp` builder — those live in ADR-048's task.
* No promotion of `delta_iev` to a *required* field yet (ADR-048 keeps it optional
  until multi-snapshot capture is reliably landed — i.e. after this task).

## 5. Architecture Impact Assessment

* Layers touched:
  * Domain — **No.**
  * Application — **No** (writer already appends; `get_iev_delta` already computes).
  * Infrastructure — **No** (no schema/repo change).
  * Adapter / Ops — **Yes, thin** (`install_cron.sh` cron entries only; optionally a
    single pre-open capture loop instead of N cron lines).
* Affects determinism? No.
* Persistence changes? No schema change — this only produces *more rows per day* via
  the existing append path.
* Orchestration/policy inside an adapter? **No** — scheduling only.

```md
Layer plan:
- Domain: not touched
- Application: not touched (get_iev_delta / save_snapshot already support the path)
- Infrastructure: not touched (iev_snapshot_history append already correct)
- Adapter: thin — cron cadence in install_cron.sh (or a small pre-open capture loop)
```

## 6. Implementation Notes & Considerations

* **Browser churn.** Each `saham fetch iev` boots a Playwright/Stockbit session.
  Keep ticks **≥ 2–3 minutes apart** so a slow run does not overlap the next. If
  session startup cost is high, prefer a **single pre-open loop** (see existing
  `loop_intraday.sh`) that reuses one session and captures at intervals, over N
  independent cron lines. Trade-off: cron-per-tick is simpler and crash-isolated;
  a loop is cleaner and lighter on session setup.
* **NCP-locked tick.** At least one tick **inside [08:56, 09:00)** so a committed
  (`is_ncp_locked = 1`) row is captured. Decision write is separate:
  `saham research pre-open capture` (not `learn snapshot`, which was removed).
* **Exact minutes are config/ops choices**, not architecture. The set above is a
  starting point; the only hard requirement is ≥ 2 pre-lock rows + ≥ 1 locked row.
* **JSON sidecar overwrites** (`data/iev/<date>/iev.json` keeps only the last tick).
  That is fine — `iev_snapshot_history` (SQLite) is the authority for delta/learning.
* **Laptop-asleep risk** — pre-existing for host cron on macOS; the earlier ticks
  are the same reliability bet as the current 08:55 tick.

## 7. Acceptance Criteria

* [ ] After a trading day, `iev_snapshot_history` holds **≥ 2 rows** for tickers
      present in multiple ticks.
* [ ] `get_iev_delta(today)` returns a **non-empty** map (ΔIEV visible in the
      `saham fetch iev` output's ΔIEV column).
* [ ] At least one captured row per day has `is_ncp_locked = 1`, stamped inside
      [08:56, 09:00) WIB.
* [ ] `install_cron.sh` is idempotent and re-installs the multi-tick block cleanly
      (no duplicate/stale saham cron entries).
* [ ] No writer/schema change; existing IEV tests remain green.

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
