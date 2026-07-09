# Rescale Foreign Flow Score from 0–120 to 0–100

## Context

`screen accum` currently shows two differently-scaled scores side by side: the accumulation screener's composite `foreign_flow_score` (0–120 "soft cap") and SignalEngine's `signal_score` (0–100). This dual-scale design is confusing — the same-looking number means different things depending on which panel it's in — and was flagged as a design smell worth fixing on its own.

This is an explicit **breaking calibration change**, not a cosmetic rename. Every absolute threshold tuned against the 0–120 scale must be converted on purpose, and the cross-system dependency where SignalEngine normalizes `foreign_flow_score` into `SignalContext.foreign_flow_quality` must move in lockstep or normalization silently breaks for new candidates.

This plan went through two review rounds after the initial draft: a Plan-agent design pass, then a manual review that found several consumers missed by both the initial exploration and the Plan agent (`today_commands.py`'s unconfigured hardcoded thresholds, a second/independent threshold set in `swing_config.py` + a pre-existing *inconsistent* fallback in `analyze_swing_display.py`, and `accumulation_journal.py` bucketing **persisted** — not live-recomputed — journal entries). Every claim from that review pass was independently re-verified against the actual code before being added here; one claim (`config/default.yaml`'s `min_foreign_flow_score`) turned out to be **dead/unused config** on verification, not a live consumer as first reported — corrected below.

**Binding decisions:**
1. **Historical persisted data is left untouched.** No migration script rewrites old SQLite/JSON/CSV records. `ForeignFlowScoreBreakdown.to_dict()` already stores `max_score` alongside every score, so old records stay self-describing.
2. **Threshold conversion: proportional preserve.** Every absolute threshold is divided by 1.2 (1 decimal), preserving identical pass/fail behavior for every existing candidate, before rounding. Table below is authoritative.
3. **`sqlite_watchlist_repository.py` gets no schema change.** Watchlist feature is unused. Documented as an accepted limitation in the ADR only.
4. **Include a formal ADR** amending ADR-030, since it documents the 0-120 scale as an accepted decision (required by this repo's own `PROMPT_CONTRACT.md`).

**Key validation finding (de-risks decision #1 for the *audit* path):** `AccumulationAuditUseCase.execute` always recomputes `foreign_flow_score` live via `ScoreForeignFlowUseCase` on the current scale — it never reconstructs a `ForeignFlowScoreBreakdown` from a persisted historical record, and `foreign_flow_quality_from_foreign_flow_score` (signal_engine.py:197) has no per-candidate max_score parameter; its only caller always passes a freshly-computed score. No code path feeds a historical 0-120 score through the new 0-100 config divisor. Audit bucket edges can stay as absolute new-scale numbers.

**Different finding for the *journal* path (new this round):** `AccumulationJournalService.review()` (`src/application/services/accumulation_journal.py`) buckets `foreign_flow_score` from **persisted** `AccumulationJournalEntry` CSV rows — real historical data, not recomputed. Per decision #1 (no data migration) this is accepted as a documented limitation: journal review bucket **labels** for entries logged before the rescale may shift under the new bucket edges (a score that used to read "40–69" may now read differently), but no data is lost or rewritten — purely a reporting/labeling artifact. Same shape of tradeoff already accepted for watchlist (decision #3) and audit-exported-artifacts.

## Calibration table (authoritative — ÷1.2, rounded to 1 decimal)

| Item | Old | New |
|---|---|---|
| max_score (scoring policy + signal_engine input_mapping) | 120.0 | 100.0 |
| consistency.weight | 40.0 | 33.3 |
| streak.weight | 30.0 | 25.0 |
| vwap_discount.weight | 20.0 | 16.7 |
| rsi_headroom.weight | 10.0 | 8.3 |
| foreign_flow_ratio.weight | 10.0 | 8.3 |
| bb_squeeze.weight (stays disabled) | 10.0 | 8.3 |
| bci.cluster_points | 15.0 | 12.5 |
| bci.stable_points | 5.0 | 4.2 |
| accumulation_screener display: enter_min | 70.0 | 58.3 |
| accumulation_screener display: watch_min | 40.0 | 33.3 |
| accumulation_screener display: coiled_spring_min | 60.0 | 50.0 |
| setup gate: foreign-bounce | 70 | 58.3 |
| setup gate: coiled-spring | 60 | 50.0 |
| setup gate: smart-money-confirmed | 60 | 50.0 |
| setup gate: pullback-continuation | 55 | 45.8 |
| audit bucket_edges.foreign_flow_score | [40, 70] | [33.3, 58.3] |
| audit `_score_bucket()` dead-code literals | 70 / 40 | 58.3 / 33.3 |
| **swing_config.py verdict thresholds:** enter_min_score | 70.0 | 58.3 |
| swing_config.py: watch_min_score | 40.0 | 33.3 |
| swing_config.py: strong_min_score | 70.0 | 58.3 |
| swing_config.py: building_min_score | 60.0 | 50.0 |
| swing_config.py: coiled_spring_min_score | 60.0 | 50.0 |
| **today_commands.py hardcoded (no config):** green threshold | 80 | 66.7 |
| today_commands.py: yellow threshold | 60 | 50.0 |
| **analyze_swing_display.py fallback `SwingDisplayConfig(...)` (pre-existing inconsistent literals — see note below):** enter_min_score | 70 | 58.3 |
| analyze_swing_display.py fallback: watch_min_score | 50 | 41.7 |
| analyze_swing_display.py fallback: coiled_spring_min_score | 70 | 58.3 |
| analyze_swing_display.py fallback: strong_min_score | 80 | 66.7 |
| analyze_swing_display.py fallback: building_min_score | 60 | 50.0 |
| **accumulation_journal.py bucket literals:** | 70 / 40 | 58.3 / 33.3 |
| **dead config (verified unused, update anyway for consistency):** config/default.yaml `swing.min_foreign_flow_score` | 70.0 | 58.3 |
| dead config: app_config.py `SwingDefaults.min_foreign_flow_score` | 70.0 | 58.3 |
| config/user.yaml.example (template, not live-loaded) | 70 | 58.3 |

Do **not** touch: `saturate_pct`/`saturate_at` fields, RSI value thresholds (25/40/75), streak counts, `coiled_spring_bb_pctile`, `filters.min_foreign_flow_score.value`/`config/analyze_swing.yaml`'s `min_foreign_flow_score: 0.0` (both disabled no-op filters), and **`SignalClassificationConfig`** in `assess_signal_use_case.py` (`strong_min_score=70`, `moderate_min_score=45`) — this classifies the *unrelated* 0-100 `SignalAssessment.score`, not `foreign_flow_score`, despite the confusingly similar field names. Verified by tracing `_classify_strength()` in `assess_signal_evidence_use_case.py:528` — it receives `SignalAssessment.score`, never `foreign_flow_score`.

**Note on the analyze_swing_display.py fallback:** its hardcoded `SwingDisplayConfig(enter_min_score=70, watch_min_score=50, coiled_spring_min_score=70, strong_min_score=80, building_min_score=60, ...)` (~line 1099) already didn't match `swing_config.py`'s canonical defaults (70/40/70/60/60) *before* this change — a pre-existing drift, not introduced here. Convert its literals proportionally anyway so it doesn't drift further, but do not attempt to unify the two paths — that's unrelated cleanup out of scope for this rescale.

**Note on cap math:** new weights sum to 116.6 raw (108.3 with bb disabled) vs. new cap 100.0 — proportionally identical shape to the old 140→120 relationship.

**Known accepted rounding edge case:** proportional conversion is behavior-preserving only *before* rounding. A candidate scoring exactly at an old boundary (e.g. precisely 70.0) maps to 58.33, but the new gate is 58.3 (1-decimal rounding) — a hairline case where an exact-boundary candidate could flip classification. Phase 8 tests must include explicit boundary cases at the old values 70, 60, 55, 40 to confirm this is the only drift class introduced.

## Implementation order

**Phase 0 — Pre-flight grep gate (run before AND after implementation):**
```bash
rg -n "0-120|120\.0|70\.0|60\.0|55\.0|40\.0|foreign_flow_score" \
  src tests config docs README.md CLI_README.md ARCHITECTURE_DECISIONS.md
```
Before starting: confirm every hit is accounted for in this doc's phases (already true as of this writing — see "Verified consumer inventory" below). After implementation: re-run and confirm zero unexplained `120.0`/`0-120` hits remain outside of comments explicitly describing historical/legacy behavior (e.g. the ADR's own description of the old scale, or the accepted-limitation notes about pre-rescale data).

**Phase 1 — Domain (leaf, no inbound deps):**
- [x] `src/domain/value_objects/foreign_flow_score_breakdown.py:21` — `max_score` default 120.0 → 100.0.
- [x] `src/domain/value_objects/foreign_flow_evidence.py:189,191` — ratio literals `(70.0/120.0)` → `(58.3/100.0)`, `(40.0/120.0)` → `(33.3/100.0)`. Cosmetic only — `score_ratio = composite_score/max_score` already generic.
- [x] `src/domain/value_objects/screen_snapshot.py:24` — update `# 0-120` comment.

**Phase 2 — Application:**
- [x] `src/application/use_case/score_foreign_flow_use_case.py` — `ForeignFlowScorePolicy` defaults (~54-74) + `BciEvidencePolicy` (~49-50): all 9 values per table.
- [x] `src/application/use_case/accumulation_screen_use_case.py:267` — comment update.
- [x] `src/application/use_case/accumulation_audit_use_case.py`:
  - `AuditBucketPolicy.foreign_flow_score` (line 45): `(40.0, 70.0)` → `(33.3, 58.3)`.
  - Add comment at the policy field + `_range_bucket` call site (~592): edges are live 0-100 scale; audit always recomputes fresh; previously-exported audit artifacts are on their era's scale.
  - `_score_bucket()` (798-803, confirmed dead/unreferenced via grep across src/ and tests/): update literals and labels for consistency; do not delete (unrelated cleanup).
- [x] `src/application/use_case/assess_signal_use_case.py` — `ForeignFlowScoreMappingConfig.max_score` 120.0 → 100.0. Leave `SignalClassificationConfig` untouched (out of scope, different score system).
- [x] `src/application/services/accumulation_journal.py` (~254-278) — `_foreign_flow_score_buckets()` literals 70/40 → 58.3/33.3. Add a comment noting the accepted limitation: entries logged before the rescale may report a different bucket label than when they were logged (labels only, no data change).

**Phase 3 — Infrastructure config loaders (Python fallbacks, must mirror YAML):**
- [x] `src/infrastructure/config/accumulation_screener_config.py` — `AccumulationDisplayConfig` defaults (40-42) + evidence/component defaults.
- [x] `src/infrastructure/config/swing_config.py` — two field groups: (a) per-setup `min_foreign_flow_score` gates (50, 63, 73, 84), and (b) verdict thresholds `enter_min_score`/`watch_min_score`/`strong_min_score`/`building_min_score`/`coiled_spring_min_score` (~95-102). Confirmed via grep: **no `verdicts:` YAML section exists in any config file**, so (b) always resolves to these Python defaults today — update them directly since there's no live YAML override path yet.
- [x] `src/application/use_case/evaluate_swing_setup_use_case.py` — same 4 per-setup config dataclass defaults.
- [x] `src/infrastructure/config/accumulation_audit_config.py` — verify only (reads `AuditBucketPolicy` default from Phase 2, no independent literal).
- [x] `src/application/services/bootstrap.py:213` — `foreign_flow_score_mapping.get("max_score", 120.0)` → `100.0`.
- [x] `src/infrastructure/config/app_config.py:94` — `SwingDefaults.min_foreign_flow_score` 70.0 → 58.3. **Verified dead config**: `get_swing_default()` (the only accessor for `APP_CFG.swing.*` fields) is called exactly once in the codebase, with key `"capital"` — never `"min_foreign_flow_score"`. Update anyway for consistency; zero behavior impact confirmed.

**Phase 4 — YAML config (land with matching Phase 3 fallback in the same change):**
- [x] `config/accumulation_screener.yaml` — `evidence.max_score`, all 8 component weights, 3 display thresholds.
- [x] `config/signal_engine.yaml:61` — `input_mapping.foreign_flow_score.max_score` 120.0 → 100.0. **Critical** normalization divisor.
- [x] `config/swing_setups.yaml` — 4 `gates.min_foreign_flow_score` values.
- [x] `config/accumulation_audit.yaml` — same 4 setup thresholds + `bucket_edges.foreign_flow_score: [40, 70]` → `[33.3, 58.3]`.
- [x] `config/default.yaml:83` — `swing.min_foreign_flow_score` 70.0 → 58.3 (dead config, see Phase 3 note).
- [x] `config/user.yaml.example:22` — value 70 → 58.3, comment "(0-120)" → "(0-100)". Template only, not live-loaded.

**Phase 5 — Adapter/CLI:**
- [x] `src/adapters/cli/screen_accum_display.py` — "SCORE (0–120)" header, "0-120" legend (~814, 950).
- [x] `src/adapters/cli/screen_accum_commands.py` — `--min-foreign-flow-score` help text + docstring.
- [x] `src/adapters/cli/today_commands.py:165,167` — hardcoded `>= 80` / `>= 60` color thresholds (confirmed: no config binding at all) → `>= 66.7` / `>= 50.0`.
- [x] `src/adapters/cli/analyze_swing_display.py`:
  - `signal_label()` (~146-162) reads `SwingDisplayConfig` fields — auto-correct once Phase 3's `swing_config.py` values are fixed and properly wired through to construction of this config object; verify the wiring site.
  - The standalone fallback `config or SwingDisplayConfig(enter_min_score=70, watch_min_score=50, coiled_spring_min_score=70, strong_min_score=80, building_min_score=60, ...)` (~line 1099) — update its 5 literals per table (pre-existing inconsistency, not unified here — see note above).

**Phase 6 — Docs:**
- [x] `README.md` — "(0-120 soft cap)" (644, 661).
- [x] `CLI_README.md:2019` — "(0-120)" → "(0-100)". Aside: this line documents a flag `--min-accum-score` that doesn't match the actual CLI flag `--min-foreign-flow-score` — a pre-existing, unrelated doc bug; not fixing the name mismatch here, only the scale.
- [x] `docs/screener-foreign-accumulation.md:138` — component-weight breakdown table; update values or add "rescaled — see ADR-039" note.
- **Out of scope (found via final grep sweep, not fixed):** `docs/building_block_swing_trade.md:353`, `docs/workflow_swing_foreign_accumulation.md:105,134,223`, `docs/claude_signal_risk_230626.md:20,45` still say "0-120". These are unlinked historical/design-log docs (not referenced from README.md or CLI_README.md), analogous to the dated `claude_signal_risk_230626.md` planning note. Left unchanged — update only if/when they're promoted to live user-facing docs.

**Phase 7 — ADR:**
- [x] `ARCHITECTURE_DECISIONS.md` — append **ADR-039: Foreign Flow Score Rescale to 0-100 (Amends ADR-030)** at the end (after ADR-038, same pattern ADR-037 used for ADR-032). Capture: rationale, full calibration table, proportional-preserve strategy, historical-data-untouched stance, and **three** accepted limitations: watchlist repo unchanged; previously-exported audit artifacts remain on their era's scale; accumulation journal review bucket labels for pre-rescale entries may shift (labels only, no data loss).

**Phase 8 — Tests (land last):**
- [x] `tests/application/use_case/test_score_foreign_flow.py`, `test_score_foreign_flow_bb_exclusion.py` — new weight/max_score expectations.
- [x] `tests/domain/test_foreign_flow_evidence.py` (~20) — fixture + confirmation-status thresholds.
- [x] `tests/adapters/cli/test_screen_accum_bb_diagnostic_display.py` (~62), `tests/adapters/cli/test_swing_commands.py` (~1826) — fixture `max_score` 120→100.
- [x] `tests/application/use_case/test_accumulation_screen.py:731` — stub `min(flow_score, 120.0) / 120.0` → `/100.0`.
- [x] `tests/infrastructure/config/test_accumulation_screener_config.py`, `tests/adapters/cli/test_swing_config.py` — loader expectations for new weights/thresholds (including the swing_config.py verdict-threshold group).
- [x] `tests/application/services/test_accumulation_journal.py` (~460-515, `test_foreign_flow_score_buckets_partition_at_70_and_40`) — update bucket edges and rename/update test to reflect new partition points.
- [x] Audit tests referencing bucket edges `[40,70]` or setup thresholds.
- [x] SignalEngine normalization tests — a candidate scoring 100 must yield `foreign_flow_quality == 1.0`.
- [x] **New:** explicit boundary-case tests at the old threshold values (70, 60, 55, 40) for every gate/bucket, asserting the proportional-converted new threshold produces the identical MATCH/PARTIAL/NO_MATCH or bucket classification as the old threshold did pre-rescale (per the rounding-drift note above).

## Verification

```bash
# Pre-flight grep gate (Phase 0) — run first
rg -n "0-120|120\.0|70\.0|60\.0|55\.0|40\.0|foreign_flow_score" \
  src tests config docs README.md CLI_README.md ARCHITECTURE_DECISIONS.md

# Targeted suite
.venv/bin/python -m pytest \
  tests/application/use_case/test_score_foreign_flow.py \
  tests/application/use_case/test_score_foreign_flow_bb_exclusion.py \
  tests/domain/test_foreign_flow_evidence.py \
  tests/application/use_case/test_accumulation_screen.py \
  tests/infrastructure/config/test_accumulation_screener_config.py \
  tests/adapters/cli/test_swing_config.py \
  tests/adapters/cli/test_swing_commands.py \
  tests/adapters/cli/test_screen_accum_bb_diagnostic_display.py \
  tests/application/services/test_accumulation_journal.py -q

# Audit + signal-engine normalization
.venv/bin/python -m pytest tests -k "audit or signal_engine" -q

# Full suite
.venv/bin/python -m pytest -q

# Manual CLI smoke tests
.venv/bin/saham screen accum INDF                     # header "SCORE (0–100)", no score > 100
.venv/bin/saham screen accum INDF --format json        # max_score == 100.0
.venv/bin/saham today                                  # today_commands.py color thresholds
.venv/bin/saham analyze swing INDF                     # signal_label() classification unchanged
```

**Behavior-preserving check:** pick a ticker whose current score sits near an old gate boundary (~70) and confirm ENTER/WATCH classification and setup MATCH/PARTIAL/NO_MATCH are unchanged before/after (outside the documented rounding edge case).

---

## Status: Implemented and verified (2026-07-09)

All 8 phases complete. Full suite: **2851 passed**, no regressions. Manual CLI smoke tests confirmed: `screen accum` shows `SCORE (0–100)` header and `max_score: 100.0` in JSON; `today` and `analyze swing` render correctly on the new scale.

**4 additional test fixes found only by running the suite** (not caught by the pre-flight grep or either exploration pass — a good reminder that grep sweeps find *consumers*, not always every *assertion* tied to a consumer):
- `test_bci_cluster_when_three_or_more_tier1_codes_are_net_buyers` / `test_bci_stable_when_one_or_two_tier1_codes_are_net_buyers` (`test_accumulation_screen.py`) — asserted old `inst` breakdown values 15.0/5.0, updated to 12.5/4.2.
- `test_signal_context_builder_derives_forward_pe_and_preserves_insider_ratio` (`test_signal_context_builder.py`) — fixture used `foreign_flow_score=60.0` to hit an exact 0.5 ratio; changed to 50.0 to preserve the ratio on the new 100-scale divisor.
- `test_broker_quality_note_supports_watch_when_smart_buying` (`test_swing_commands.py`) — used `score=68` specifically chosen to sit just below the *old* 70 gate (to force a PARTIAL match for the "watchlist priority" message branch); 68 is now *above* the new 58.3 gate, flipping it to MATCH and the wrong message branch. Changed to 56.0, which stays below the new gate. Audited every other `_candidate(score=...)` call in the same file for the same near-boundary risk — all others sit safely away from both old and new thresholds.

## Post-implementation review round (2026-07-09): 4 more findings, all fixed

An independent review of the merged change caught issues the implementation pass missed:

1. **HIGH — `src/application/services/flow_confirmation_evidence_builder.py` had its own independent, unrescaled copy of the component weights** (`_FLOW_SIGNAL_WEIGHTS` = 40/30/20/10/15, `_FLOW_MAX_SCORE` = 115.0), never wired to `ForeignFlowScorePolicy` or caught by any grep pattern used during implementation. Because the builder normalizes the (now smaller, rescaled) breakdown scores by the old denominator, it silently *underestimated* flow strength — e.g. a candidate whose old proportional strength was 0.904 would compute to 0.753 instead of the correct 0.904. This feeds `FlowConfirmationEvidence.capped_strength`, which SignalEngine's canonical `institutional_flow` evidence group scores from — a real production scoring regression, not just cosmetic drift. **Fixed:** weights rescaled to 33.3/25.0/16.7/8.3/12.5; `_FLOW_MAX_SCORE` now derived as `sum(_FLOW_SIGNAL_WEIGHTS.values())` (95.8) instead of a second hardcoded literal, so it can't drift out of sync again. Updated `test_flow_confirmation_evidence_builder.py` fixtures and the `104.0` → `86.6` assertion accordingly.
2. **MEDIUM — `setup_phase.thresholds.accumulation_min_flow_score` (60.0) was stale** in `config/swing_setups.yaml`, `setup_phase_detector.py`, and the tuner bounds in `swing_tuning_patch_validator.py`. Confirmed (again) it's not read by `_constructive_phase()`'s actual accumulation-gate logic — not an active behavior bug today, but a stale-scale trap for future tuning. **Fixed:** rescaled to 50.0 in both config and Python default, with an explicit comment stating it's currently unused. While investigating this, also found and fixed the **same bug pattern on the active (non-dead) field**: `swing_tuning_patch_validator.py`'s bounds for `setups.*.gates.min_foreign_flow_score` were still `(30, 90, 1, 5)` — rescaled to `(25.0, 75.0, 1.0, 4.0)`.
3. **LOW — ADR-030 had no pointer to ADR-039.** Added an "Amended by" line under ADR-030's header plus an inline note next to its "0-120" mention.
4. **LOW — `CLI_README.md` still named the non-existent `--min-accum-score` flag** (pre-existing bug, touched again this round so fixed now) in 3 places; corrected to the real flag `--min-foreign-flow-score`.

