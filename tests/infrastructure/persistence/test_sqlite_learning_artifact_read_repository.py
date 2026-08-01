"""Read-only learning repository must not create DB files or schema."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactReadRepository,
    SQLiteLearningArtifactRepository,
)


def test_read_repo_refuses_missing_database(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "missing.db"
    assert not missing.exists()
    with pytest.raises(FileNotFoundError, match="does not exist"):
        SQLiteLearningArtifactReadRepository(missing)
    assert not missing.exists()
    assert not missing.parent.exists() or not any(missing.parent.iterdir())


def test_write_repo_creates_schema_but_read_repo_does_not_on_missing(
    tmp_path: Path,
) -> None:
    # Control: write repo creates path+schema (existing behavior for capture).
    write_path = tmp_path / "write.db"
    SQLiteLearningArtifactRepository(write_path)
    assert write_path.is_file()
    size = write_path.stat().st_size
    assert size > 0

    # Read repo works against existing DB and lists without writes.
    read_repo = SQLiteLearningArtifactReadRepository(write_path)
    assert read_repo.list_observations(AssessmentPurpose.ACCUMULATION_DISCOVERY) == ()
    assert write_path.stat().st_size == size


def test_read_repo_has_no_write_methods() -> None:
    for name in (
        "add_observation",
        "add_label",
        "add_policy_snapshot",
        "add_policy_snapshots_atomic",
        "add_evaluation",
    ):
        assert not hasattr(SQLiteLearningArtifactReadRepository, name)
