#!/usr/bin/env python3
"""Clean-break purge of ACCUMULATION_DISCOVERY learning corpus.

Default is dry-run. Pass ``--execute`` to delete.

Blast radius (see task 04 re-vet):
  - track snapshots + labels for accum observation_ids (FK-first)
  - accum evaluations + observations
  - accum purpose policy snapshots
  - full setup_phase_ledger (rebuilt from new observations)

PRE_OPEN / SWING observations and their labels are never deleted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.infrastructure.config.app_config import load_app_config  # noqa: E402
from src.infrastructure.persistence.purge_accum_learning_corpus import (  # noqa: E402
    purge_accum_learning_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None, help="SQLite path (default: app config)")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default is dry-run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable report JSON",
    )
    args = parser.parse_args()
    db = args.db or Path(load_app_config().storage.db_path)

    report = purge_accum_learning_corpus(db, execute=args.execute)
    c = report.counts

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"db: {report.db_path}")
        print(f"accum observations: {c.accum_observations}")
        print(f"track snapshots (accum): {c.track_snapshots}")
        print(f"labels for those obs: {c.labels}")
        print(f"accum evaluations: {c.evaluations}")
        print(f"accum policy snapshots: {c.policy_snapshots}")
        print(f"setup_phase_ledger rows: {c.phase_ledger_rows}")
        print(f"non-accum observations (untouched): {c.non_accum_observations}")
        print(f"non-accum labels (untouched): {c.preopen_labels}")
        if report.foreign_key_violations:
            print(f"foreign_key_violations: {report.foreign_key_violations}")
            return 2
        if not report.executed:
            print("dry-run only; pass --execute to delete")
        else:
            print("deleted.")

    if report.foreign_key_violations:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
