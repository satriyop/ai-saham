#!/usr/bin/env python3
"""ADR-056 clean break: delete ACCUMULATION_DISCOVERY learning rows only.

Does not touch pre-open observations, tracks, or labels.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Allow running as scripts/purge_... from repo root
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.infrastructure.config.app_config import load_app_config  # noqa: E402


def _connect(db: Path) -> sqlite3.Connection:
    """Open SQLite with mandatory FK enforcement (same as learning repo)."""
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    enabled = con.execute("PRAGMA foreign_keys").fetchone()[0]
    if enabled != 1:
        con.close()
        raise RuntimeError("SQLite foreign key enforcement is required")
    return con


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None, help="SQLite path (default: app config)")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default is dry-run)",
    )
    args = parser.parse_args()
    db = args.db or Path(load_app_config().storage.db_path)
    con = _connect(db)

    obs_ids = [
        r["observation_id"]
        for r in con.execute(
            "SELECT observation_id FROM learning_observations "
            "WHERE purpose = 'ACCUMULATION_DISCOVERY'"
        )
    ]
    n_obs = len(obs_ids)
    n_labels = 0
    if obs_ids:
        placeholders = ",".join("?" * len(obs_ids))
        n_labels = con.execute(
            f"SELECT COUNT(*) AS c FROM learning_outcome_labels "
            f"WHERE observation_id IN ({placeholders})",
            obs_ids,
        ).fetchone()["c"]
    n_eval = con.execute(
        "SELECT COUNT(*) AS c FROM learning_evaluations "
        "WHERE purpose = 'ACCUMULATION_DISCOVERY'"
    ).fetchone()["c"]
    n_preopen = con.execute(
        "SELECT COUNT(*) AS c FROM learning_observations "
        "WHERE purpose != 'ACCUMULATION_DISCOVERY'"
    ).fetchone()["c"]

    print(f"db: {db}")
    print(f"accum observations: {n_obs}")
    print(f"labels for those obs: {n_labels}")
    print(f"accum evaluations: {n_eval}")
    print(f"non-accum observations (untouched): {n_preopen}")

    if not args.execute:
        print("dry-run only; pass --execute to delete")
        con.close()
        return 0

    if obs_ids:
        placeholders = ",".join("?" * len(obs_ids))
        con.execute(
            f"DELETE FROM learning_outcome_labels WHERE observation_id IN ({placeholders})",
            obs_ids,
        )
    con.execute("DELETE FROM learning_evaluations WHERE purpose = 'ACCUMULATION_DISCOVERY'")
    con.execute("DELETE FROM learning_observations WHERE purpose = 'ACCUMULATION_DISCOVERY'")
    con.commit()
    print("deleted.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
