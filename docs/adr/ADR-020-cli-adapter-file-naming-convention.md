# ADR-020: CLI Adapter File Naming Convention

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — CLI command/display filenames follow command-tree ownership, subject to documented legacy files.
**Decision**
CLI command implementation files are named after their position in the command tree:
`{top_command}_{sub_command}_commands.py` for command files and
`{top_command}_{sub_command}_display.py` for display/formatting files.

Examples: `saham analyze swing` → `analyze_swing_commands.py`; `saham analyze regime` → `analyze_regime_commands.py`; swing-specific trade tools (`backtest-swing`, `size`) → `trade_swing_commands.py`.

**Rationale**
A flat CLI adapter directory becomes unreadable as the command surface grows. Embedding the command hierarchy in the filename makes ownership visible without opening the file, and prevents the silent mixed-group problem where one file serves both `saham analyze` and `saham trade` commands.

**Implications**

* New command files must follow this convention from creation.
* A file serving only one command group gets exactly one prefix segment (e.g., `analyze_swing_commands.py`).
* A display file paired with a command file mirrors its prefix (e.g., `analyze_swing_display.py`).
* Legacy cross-group files are not the target shape. Split them when a focused command-group cleanup is already in scope; do not rename them as incidental churn in unrelated feature work.
* Accumulation and swing command/display files already follow this convention (`screen_accum_commands.py`, `trade_accum_commands.py`, `analyze_accum_commands.py`, `analyze_swing_display.py`, `trade_swing_display.py`).

**Exceptions**

* Files serving multiple top-level groups may keep their current names until a dedicated split is made.
* Shared infrastructure not tied to a specific command (e.g., a `_swing_helpers.py`) may omit the top-command prefix.
