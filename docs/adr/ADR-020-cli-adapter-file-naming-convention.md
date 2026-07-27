# ADR-020: CLI Adapter File Naming Convention

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — CLI command/display filenames follow
command-tree ownership. Examples refreshed 2026-07-27 after the paper-only
`trade` / corpus `research` / `policy` clean break (public tree in ADR-049).

**Decision**

CLI command implementation files are named after their position in the command
tree:

```text
{top_command}_{sub_command}_commands.py   # Typer handlers for that node
{top_command}_{sub_command}_display.py    # display / formatting for that node
```

Optional role suffixes for non-handler helpers that still belong to one node:

```text
{top_command}_{sub_command}_workflow_factory.py
{top_command}_{sub_command}_*_runner.py
{top_command}_{sub_command}_actions.py
```

Root routers stay at `{top_command}_commands.py` (e.g. `trade_commands.py`,
`policy_commands.py`, `research_commands.py`) and only register scenario
sub-apps.

**Examples (current)**

| Public command | Adapter file |
|----------------|--------------|
| `saham analyze swing` | `analyze_swing_commands.py` |
| `saham analyze regime` | `analyze_regime_commands.py` |
| `saham screen accum` | `screen_accum_commands.py` |
| `saham screen pre-open` | `screen_pre_open_commands.py` |
| `saham research pre-open capture` | `research_pre_open_capture_commands.py` |
| `saham research accum …` | `research_accum_*_commands.py` |
| `saham trade pre-open …` | `trade_pre_open_commands.py` |
| `saham trade accum …` | `trade_accum_commands.py` |
| `saham policy accum …` | `policy_accum_lifecycle_commands.py`, `policy_accum_backtest_commands.py`, … |

**Rationale**

A flat CLI adapter directory becomes unreadable as the command surface grows.
Embedding the command hierarchy in the filename makes ownership visible without
opening the file, and prevents the silent mixed-group problem where one file
serves both `saham analyze` and `saham trade` commands (or paper vs policy vs
corpus).

**Implications**

* New command files must follow this convention from creation.
* A file serving only one command group gets exactly one top-command prefix
  (e.g. `analyze_swing_commands.py`, not `shared_swing_commands.py`).
* A display file paired with a command file mirrors its prefix
  (e.g. `policy_accum_backtest_display.py`).
* When a public command **moves** between top-level groups, rename adapters in
  the same clean-break change so filename ownership matches the tree (e.g.
  former `trade_swing_*` policy lifecycle → `policy_accum_*`).
* Legacy cross-group files are not the target shape. Split them when a focused
  command-group cleanup is already in scope; do not rename them as incidental
  churn in unrelated feature work.

**Exceptions**

* Files serving multiple top-level groups may keep their current names until a
  dedicated split is made.
* Shared infrastructure not tied to a specific command (e.g. a small helpers
  module used by one family only) may use a narrower family prefix
  (`research_learning_helpers.py`) rather than a full scenario path.
* Application/domain module names (e.g. `swing_policy_learning_use_case.py`)
  are **not** governed by this ADR; only `src/adapters/cli/` ownership is.

**Retired examples (do not use)**

* `trade_swing_*` for policy lifecycle or sizing (policy moved; size CLI retired)
* `trade_intraday_*` for pre-open paper or proxy sim under trade
* `research_signal_*` for accum corpus (use `research_accum_*`)
* `trade_log_router_*` flag-router patterns that bypass scenario files

Public command family jobs (`trade` paper / `research` corpus / `policy`
config) are specified in [ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md)
Public CLI section — this ADR only binds **filename ownership** to that tree.
