# Database-Owned Pre-Open Learning Workflow

The pre-open learning lifecycle is deterministic and SQLite-owned. Production
decisions use NCP-locked evidence collected wholly inside 08:56–08:58 WIB.

**Operator day path:** [runbook_pre_open.md](runbook_pre_open.md)
(two lanes, three artifacts, cron clock, retired commands).

## Workflow

```text
NCP-locked capture
→ immutable pre-open observations
→ 09:00–09:30 track snapshots
→ one open_30m label per observation
→ compatible-session evaluation
```

```bash
saham fetch iev
saham research pre-open capture
saham research pre-open track
saham assess pre-open                    # post-open assess (human, not cron)
saham trade pre-open log \         # paper notebook (human)
  --observation-id … --opening-snapshot-id …
saham research pre-open labels
saham research pre-open evaluate
saham research pre-open status
```

`capture` persists both pass and reject decisions in
`learning_observations`. `track` links samples to their stable
`observation_id` in `learning_track_snapshots`. `labels` generates immutable
`price_path.open_30m.v1` outcomes in `learning_outcome_labels`.

`assess pre-open` is **not** a learning write: it re-reads observation + track
for post-open ENTER/WAIT/SKIP. Paper log is a personal notebook, not a label.

`evaluate` reads persisted labels only. It never rereads track snapshots or
recomputes a label outcome. One-session results are descriptive; compatible
multi-session cohorts may become diagnostic, but price-path evidence cannot
become production-policy authority.

## Guardrails

- SQLite is the only durable learning-artifact store.
- Stable identity excludes `captured_at`; conflicting immutable payloads fail.
- Missing NCP provenance, source availability, or compatible cohort identity
  fails closed.
- Production signal/risk arithmetic and `TradeSetup` composition are unchanged.
- There is no grade, prompt, AI tune, JSON/Markdown export, or file fallback.
- `--format json` writes stdout only.

See [ADR-049](adr/ADR-049-database-owned-learning-pipeline-clean-break.md).
