# ADR-039: Foreign Flow Score Rescale to 0-100 (Amends ADR-030)

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted
**Date:** 2026-07-09
**Current implementation:** Current configs and newly computed foreign-flow scores use 0–100. Existing persisted history is not silently migrated and must retain scale provenance.

### Context

ADR-030 established the accumulation screener's composite `foreign_flow_score` on a 0-120 "soft cap" scale. This coexists with SignalEngine's unrelated `SignalAssessment.score`, which has always been 0-100. Showing two differently-scaled scores side by side in `screen accum` output (and in `analyze swing`, `saham today`) was a recurring source of confusion — the same-looking number means different things depending on which panel it's in.

### Decision

`foreign_flow_score` and every threshold tuned against it are rescaled from 0-120 to 0-100, via a **proportional-preserve conversion** (divide by 1.2, round to 1 decimal). This is a deliberate calibration exercise, not a mechanical global find-replace: every consumer was individually identified, verified against the live code, and converted so that pass/fail behavior for every existing candidate is unchanged (before rounding).

#### Calibration table (old → new)

| Item | Old | New |
|---|---|---|
| `ForeignFlowScorePolicy.max_score` / `signal_engine.yaml` `input_mapping.foreign_flow_score.max_score` | 120.0 | 100.0 |
| `consistency.weight` | 40.0 | 33.3 |
| `streak.weight` | 30.0 | 25.0 |
| `vwap_discount.weight` | 20.0 | 16.7 |
| `rsi_headroom.weight` | 10.0 | 8.3 |
| `foreign_flow_ratio.weight` | 10.0 | 8.3 |
| `bb_squeeze.weight` (stays disabled — see BB ownership fix, same-day prior change) | 10.0 | 8.3 |
| `bci.cluster_points` | 15.0 | 12.5 |
| `bci.stable_points` | 5.0 | 4.2 |
| Accumulation screener display: enter/watch/coiled-spring minimums | 70.0 / 40.0 / 60.0 | 58.3 / 33.3 / 50.0 |
| Setup gates: foreign-bounce / coiled-spring / smart-money-confirmed / pullback-continuation | 70 / 60 / 60 / 55 | 58.3 / 50.0 / 50.0 / 45.8 |
| Audit bucket edges (`accumulation_audit.yaml`, `AuditBucketPolicy`) | [40, 70] | [33.3, 58.3] |
| `swing_config.py` verdict thresholds (enter/watch/strong/building/coiled-spring) | 70 / 40 / 70 / 60 / 60 | 58.3 / 33.3 / 58.3 / 50.0 / 50.0 |
| `today_commands.py` display color thresholds (previously unconfigured literals) | 80 / 60 | 66.7 / 50.0 |
| `analyze_swing_display.py` fallback `SwingDisplayConfig` (pre-existing drift from `swing_config.py`'s canonical defaults, not introduced by this ADR — converted proportionally but not unified) | 70 / 50 / 70 / 80 / 60 | 58.3 / 41.7 / 58.3 / 66.7 / 50.0 |
| `accumulation_journal.py` bucket labels | 70 / 40 | 58.3 / 33.3 |
| `config/default.yaml`, `app_config.py` `SwingDefaults.min_foreign_flow_score` (verified dead/unused — `get_swing_default()` is only ever called with key `"capital"`) | 70.0 | 58.3 |
| `config/user.yaml.example` (template, not live-loaded) | 70 | 58.3 |

Explicitly **out of scope** — different score system, not touched: `SignalClassificationConfig` in `assess_signal_use_case.py` (`strong_min_score=70`, `moderate_min_score=45`) classifies the unrelated 0-100 `SignalAssessment.score`, despite confusingly similar field names to the accumulation screener's own thresholds.

#### Historical data: untouched, not migrated

No migration script rewrites persisted SQLite/JSON/CSV records. `ForeignFlowScoreBreakdown.to_dict()` already stores `max_score` alongside every score, so old records (max_score=120.0) remain self-describing. `AccumulationAuditUseCase.execute` always recomputes `foreign_flow_score` live via `ScoreForeignFlowUseCase` — it never reconstructs a `ForeignFlowScoreBreakdown` from a persisted historical record, and `SignalEngine.foreign_flow_quality_from_foreign_flow_score()` has no per-candidate max_score parameter, so no code path feeds a historical 0-120 score through the new 0-100 config divisor.

#### Accepted limitations (documented, not fixed)

1. **Watchlist repository** (`sqlite_watchlist_repository.py`) stores `flow_score` with no `max_score`/schema-version tracking. Not changed — the feature is unused. Watchlists saved before vs. after this rescale may not compare meaningfully.
2. **Previously-exported audit artifacts** (JSON/CSV from `analyze accum-audit --output`) remain on their era's scale; the new bucket edges must not be applied retroactively to them.
3. **Accumulation journal review** (`AccumulationJournalService.review()`) buckets *persisted* `AccumulationJournalEntry.foreign_flow_score` values, not live-recomputed ones. Entries logged before this rescale may report a different bucket **label** than when they were originally logged — labels only, no data loss or rewrite.

### Rationale

A proportional-preserve conversion was chosen over ad hoc recalibration because it requires no new trading-calibration judgment calls — every gate and bucket continues to admit/reject the same candidates it did before, just expressed on a scale consistent with SignalEngine. Rounding to 1 decimal introduces a documented, narrow edge case: a candidate scoring exactly at an old boundary (e.g. precisely 70.0) maps to 58.33, but the new gate is 58.3 — a hairline case where an exact-boundary candidate could flip classification. This is accepted as the cost of round numbers over floating-point exactness.

### Consequences

- `screen accum`, `analyze swing`, and `saham today` now show `foreign_flow_score` and `signal_score` on the same 0-100 scale, removing the dual-scale confusion that motivated this change.
- Full implementation tracker and file-by-file inventory: `docs/screen_refactor.md`.
