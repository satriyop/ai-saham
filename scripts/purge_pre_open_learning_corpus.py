#!/usr/bin/env python3
"""Clean-break purge of PRE_OPEN_AUCTION_DIRECTION learning rows only.

Does not touch ACCUMULATION_DISCOVERY. Default is dry-run; pass --execute.
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
from src.infrastructure.persistence.purge_pre_open_learning_corpus import (  # noqa: E402
    purge_pre_open_learning_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    db = args.db or Path(load_app_config().storage.db_path)
    report = purge_pre_open_learning_corpus(db, execute=args.execute)
    c = report.counts
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"db: {report.db_path}")
        print(f"preopen observations: {c.preopen_observations}")
        print(f"labels: {c.labels}")
        print(f"track snapshots: {c.track_snapshots}")
        print(f"evaluations: {c.evaluations}")
        print(f"accum observations (must stay): {c.accum_observations}")
        if report.foreign_key_violations:
            print(f"foreign_key_violations: {report.foreign_key_violations}")
            return 2
        if not report.executed:
            print("dry-run only; pass --execute to delete")
        else:
            print("deleted.")
    return 2 if report.foreign_key_violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
