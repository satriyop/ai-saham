# Code Convention Audit - Closed

Scope: production code under `src/**/*.py`, plus tests only when they hid
architecture violations. Documentation content was excluded from audit targets.

Audit date: 2026-07-14.

Closure date: 2026-07-14.

## Outcome

All findings from this audit pass have been implemented and vetted.

Resolved findings:

1. `src/adapters/cli/screen_pre_open_commands.py` workflow policy extraction.
2. `src/adapters/cli/analyze_commands.py` router/workflow/display split.
3. `src/adapters/cli/analyze_accum_commands.py` setup policy and wiring cleanup.
4. `src/adapters/cli/trade_swing_tuning_commands.py` tuning workflow extraction.
5. `src/application/services/swing_broker_detail_builder.py` responsibility split.
6. `src/infrastructure/browser/stockbit_base_provider.py` SQLite connection global removal.
7. Stockbit provider import-time `STOCKBIT_CFG` removal.
8. `src/infrastructure/ai/formula_translator.py` provider/output/mock split.
9. `src/adapters/cli/view_broker_commands.py` status/distribution/display split.

## Verification

Each finding was separately implementation-reviewed against its targeted harness.
The final closure should be treated as the end of this audit batch, not as an
open work queue.

Before starting another cleanup cycle, run a fresh audit from current `HEAD`
instead of reusing the resolved findings above.

## Conventions Merged Forward

Reusable conventions from this audit pass were merged into
`AI_AGENT_CHECKLIST.md`:

- CLI command modules must move non-trivial workflow/policy into application use
  cases.
- Import-time loaded config is hidden global state.
- Shared mutable infrastructure state must be explicit and injectable.
- Builder modules should describe one output shape.
- Display modules should split only when panels/tables are independently
  reusable or the filename no longer exposes what is rendered.
- Multi-provider AI adapters should split orchestration, provider transport,
  output canonicalization, and mock templates.
- CLI command groups should split status, display, provider factory, and cached
  query responsibilities once those concerns become independently searchable.
