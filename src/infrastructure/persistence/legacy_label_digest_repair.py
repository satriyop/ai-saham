"""Repair pre-open labels whose digests still include wall-clock labeled_at.

After 11bfca95, LearningOutcomeLabel digests exclude labeled_at. Rows written
before that change fail read-path integrity and abort cohort list_labels /
evaluate. This module rehashes only rows whose stored digest matches the
legacy-with-labeled_at formula; other mismatches stay fail-closed.

Layer: Infrastructure (persistence repair)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.domain.value_objects.learning_artifacts import (
    LearningContractError,
    label_has_legacy_labeled_at_digest,
    modern_label_digest,
    rehash_label_excluding_labeled_at,
    validate_artifact_integrity,
    validate_label_identity,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    _LABEL_SELECT,
    _label_expected_columns,
    _label_from_dict,
)


@dataclass(frozen=True)
class LegacyLabelDigestRepairResult:
    scanned: int
    legacy_count: int
    repaired_count: int
    already_modern_count: int
    skipped_other_mismatch_count: int
    repaired_label_ids: tuple[str, ...]
    skipped_label_ids: tuple[str, ...]
    dry_run: bool


def repair_legacy_labeled_at_label_digests(
    db_path: Path,
    *,
    dry_run: bool = True,
) -> LegacyLabelDigestRepairResult:
    """Scan learning_outcome_labels and rehash legacy labeled_at digests.

    Updates both ``artifact_digest`` and ``artifact_json`` so column recon passes.
    Idempotent: modern rows are counted and left alone.
    """

    path = Path(db_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"learning database does not exist: {path}")

    repaired_ids: list[str] = []
    skipped_ids: list[str] = []
    already_modern = 0
    legacy = 0
    other = 0
    scanned = 0

    with sqlite3.connect(str(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT {_LABEL_SELECT} FROM learning_outcome_labels ORDER BY label_id"
        ).fetchall()
        scanned = len(rows)
        for row in rows:
            raw = json.loads(row["artifact_json"])
            label = _label_from_dict(raw)
            modern = modern_label_digest(label)
            if label.artifact_digest == modern:
                already_modern += 1
                continue
            if not label_has_legacy_labeled_at_digest(label):
                other += 1
                skipped_ids.append(label.label_id)
                continue
            legacy += 1
            fixed = rehash_label_excluding_labeled_at(label)
            validate_label_identity(fixed)
            validate_artifact_integrity(fixed, id_field="label_id")
            if fixed.artifact_digest != modern:
                raise LearningContractError(
                    f"rehash produced unexpected digest for {fixed.label_id!r}"
                )
            if dry_run:
                repaired_ids.append(fixed.label_id)
                continue
            expected = _label_expected_columns(fixed)
            conn.execute(
                """
                UPDATE learning_outcome_labels
                SET artifact_digest = ?,
                    artifact_json = ?
                WHERE label_id = ?
                """,
                (
                    expected["artifact_digest"],
                    expected["artifact_json"],
                    fixed.label_id,
                ),
            )
            repaired_ids.append(fixed.label_id)
        if not dry_run and repaired_ids:
            conn.commit()

    return LegacyLabelDigestRepairResult(
        scanned=scanned,
        legacy_count=legacy,
        repaired_count=len(repaired_ids),
        already_modern_count=already_modern,
        skipped_other_mismatch_count=other,
        repaired_label_ids=tuple(repaired_ids),
        skipped_label_ids=tuple(skipped_ids),
        dry_run=dry_run,
    )
