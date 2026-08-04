"""Rehash learning labels whose digests still include wall-clock labeled_at.

Safe, idempotent corpus repair after 11bfca95 (label digests ignore labeled_at).
Only rows whose stored digest matches the legacy formula are rewritten.

Usage:
  .venv/bin/python scripts/repair_legacy_label_digests.py --db data/db/data.db
  .venv/bin/python scripts/repair_legacy_label_digests.py --db data/db/data.db --apply
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.infrastructure.persistence.legacy_label_digest_repair import (
    repair_legacy_labeled_at_label_digests,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="SQLite learning DB path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write updates (default is dry-run only).",
    )
    args = parser.parse_args()
    result = repair_legacy_labeled_at_label_digests(args.db, dry_run=not args.apply)
    print(json.dumps(asdict(result), indent=2))
    if result.skipped_other_mismatch_count:
        raise SystemExit(
            f"refusing success: {result.skipped_other_mismatch_count} non-legacy "
            "digest mismatches need manual review"
        )


if __name__ == "__main__":
    main()
