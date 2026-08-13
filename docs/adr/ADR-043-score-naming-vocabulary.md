# ADR-043: Score Naming Vocabulary

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted
**Date:** 2026-07-23
**Current implementation:** Canonical names below are enforced in source, config loaders, and new persistence writes. Legacy SQLite watchlist columns are dual-read only.

### Context

After ADR-030/039 the accumulation screener uses a 0–100 composite score built
from foreign-broker flow evidence, while SignalEngine produces a separate
0–100 `SignalAssessment.score`. The shared label `foreign_flow_score` was used
for the accumulation composite, but the same phrase also appears on unrelated
0–1 participation metrics (`TickerProfileSnapshot.foreign_flow_score`) and in
group-level signal-engine internals (`setup_score`, `flow_score`). Side-by-side
CLI/TUI panels therefore looked like they showed the same kind of number when
they did not.

### Decision

Adopt an explicit vocabulary contract. **Do not change scoring formulas or
weights** — this ADR is naming and persistence-key hygiene only.

#### Canonical score names

| Concept | Canonical name | Scale | Notes |
|---|---|---|---|
| Accumulation composite from broker-flow evidence | `accum_score` | 0–100 | Former `foreign_flow_score` (accum meaning) |
| SignalEngine staged-evidence output | `signal_score` | 0–100 | `SignalAssessment.score`; unchanged field name on assessment object |
| Setup evidence group contribution | `setup_group_score` | 0–100 | Historical rename from `setup_score`; **production group retired by ADR-067** — not a live accum evidence basis |
| Flow confirmation group contribution | `flow_group_score` | 0–100 | Renamed from `flow_score`; **sole production evidence group** for accum after ADR-067 |
| Trade setup sizing input | `signal_score` on `TradeSetup` | 0–100 | Unchanged |
| Foreign participation ratio (profile) | `foreign_flow_score` on `TickerProfileSnapshot` | 0–1 | **Excluded** — different metric, keep name |

#### Type and module renames

| Old | New |
|---|---|
| `ForeignFlowScorePolicy` | `AccumScorePolicy` |
| `ForeignFlowScoreBreakdown` | `AccumScoreBreakdown` |
| `ScoreForeignFlowUseCase` | `ScoreAccumUseCase` |
| `ScoreForeignFlowRequest` | `ScoreAccumRequest` |
| `foreign_flow_score_breakdown.py` | `accum_score_breakdown.py` |
| `score_foreign_flow_use_case.py` | `score_accum_use_case.py` |
| `ForeignFlowEvidence.composite_score` | `accum_score` property |
| `AccumScoreBreakdown.foreign_flow_score` | `accum_score` property |

#### Config YAML keys (reject old keys)

| Old key | New key |
|---|---|
| `accumulation_screener.filters.min_foreign_flow_score` | `min_accum_score` |
| `accumulation_screener.display.enter_min_foreign_flow_score` | `enter_min_accum_score` |
| `accumulation_screener.display.watch_min_foreign_flow_score` | `watch_min_accum_score` |
| `accumulation_screener.display.coiled_spring_min_foreign_flow_score` | `coiled_spring_min_accum_score` |
| `*.gate_min_foreign_flow_score` / setup gate mins | `gate_min_accum_score` / `min_accum_score` variants |
| `signal_engine.input_mapping.foreign_flow_score` | `input_mapping.accum_score` |
| screener policy block | `accum_score_policy` (loader surface) |

Loaders **reject** deprecated keys with explicit errors — no silent alias layer in YAML.

#### Watchlist persistence

`ScreenSnapshotEntry` fields:

- `flow_score` → `accum_score`
- `composite_score` → `signal_score`

SQLite `screen_snapshots`:

- **Write:** `accum_score`, `signal_score` only
- **Read:** `COALESCE(accum_score, flow_score)` and `COALESCE(signal_score, composite_score)` for legacy rows

#### Method rename

`SignalEngine.foreign_flow_quality_from_foreign_flow_score` →
`foreign_flow_quality_from_accum_score` (same normalization math).

### Explicit exclusions (unchanged names)

- `TickerProfileSnapshot.foreign_flow_score` — 0–1 participation metric
- `flow_score_ex_bb` unless compile requires otherwise
- `SignalAssessment.score` field name
- `TradeSetup.signal_score`
- `research/artifacts/*.md` historical outputs
- Persisted fingerprint key `tp_foreign_flow_score` (read compat for old observations)

### Consequences

- New code and config must use the canonical vocabulary.
- Tests and CLI output refer to "accum score" / `accum_score` for the 0–100 accumulation composite.
- Historical watchlist DB rows remain readable without migration rewrite.
- ADR-039 calibration values are unchanged; only identifiers moved.

### Non-goals

- Rescore or migrate historical observation payloads
- Rename `ForeignFlowEvidence` class (evidence family name stays)
- Rename plugin indicator `foreign_flow.py`

### Implementation pointers

- `src/domain/value_objects/accum_score_breakdown.py`
- `src/application/use_case/score_accum_use_case.py`
- `src/infrastructure/persistence/sqlite_watchlist_repository.py`
- `src/infrastructure/config/accumulation_screener_config.py`
- `src/application/services/engine_bootstrap/signal_scoring_config_resolver.py`
- `config/signal_engine.yaml`, `config/accumulation_screener.yaml`
