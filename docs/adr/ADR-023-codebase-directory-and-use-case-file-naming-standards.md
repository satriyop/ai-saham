# ADR-023: Codebase Directory and Use Case File Naming Standards

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Superseded by [ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md)
**Date:** Not recorded (legacy decision)
**Current implementation:** Historical. ADR-049 replaces file-owned learning
artifacts with database-owned contracts. General naming guidance remains useful
only where a newer ADR has not replaced it.
**Decision**
Establish strict layout and naming standards for the data directory structure, journals, and application use case files.

**Directory Structure Standards**
To separate concerns and avoid polluting the repository root:
* Databases must live under `data/db/` (e.g., `data/db/data.db`).
* Interactive sessions, temporary screeners, and state markers must live under `data/session/` (e.g., `data/session/.last-session.json`, `data/session/.last-confirmation.json`).
* Miscellaneous raw payloads, spy outputs, and developer debug dumps must live under `data/debug/`.
* Running trade/order book learning tracks were historically organized under
  `data/opening/YYYYMMDD/`; ADR-049 retires that path.
* Journal files (e.g., `journals/pre_open_paper.csv`, `journals/pre_open.csv`, `journals/trades.jsonl`) must be stored under the `journals/` directory and use snake_case naming.

**File Naming Standards**
* **Application Layer**: To explicitly identify the layer and purpose of business logic modules, all use case files under `src/application/use_case/` must use the suffix `_use_case.py` (e.g., `pre_open_screen_use_case.py`, `assess_risk_use_case.py`).
* **CLI Adapters**: Command modules and formatting displays follow the `{top_group}_{sub_group}_commands.py` and `{top_group}_{sub_group}_display.py` conventions established in ADR-020.

**Rationale**
Standardizing use case suffixes prevents namespace collisions, preserves hexagonal architecture visibility, and aligns with professional clean-architecture conventions. Isolating databases, session state files, and debug files under structured subdirectories under `data/` prevents repository pollution and ensures predictable local-first state storage.
