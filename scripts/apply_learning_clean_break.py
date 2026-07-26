"""Apply the explicitly authorized learning clean break to one SQLite file."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.infrastructure.persistence.learning_clean_break import (
    apply_learning_clean_break,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required acknowledgement that the legacy learning corpus is deleted.",
    )
    args = parser.parse_args()
    if not args.yes:
        parser.error("--yes is required for the destructive clean break")
    print(json.dumps(asdict(apply_learning_clean_break(args.db)), indent=2))


if __name__ == "__main__":
    main()
