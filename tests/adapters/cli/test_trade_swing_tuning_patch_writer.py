"""Tests for write_swing_tuning_patch_export filesystem writer."""

import json

from src.adapters.cli.trade_swing_tuning_patch_writer import (
    write_swing_tuning_patch_export,
)


def _payload(**overrides):
    defaults = dict(
        schema_version=1,
        artifact_type="swing_tuning_patch_review",
        intent="review_only_candidate_config_patch_no_apply",
        source_review={"setup": "foreign-bounce"},
        patch_items=[{"target_path": "risk.max_positions", "proposed_value": 4}],
        item_count=1,
        apply={"supported": False, "reason": "no"},
    )
    defaults.update(overrides)
    return defaults


def test_creates_parent_directory_that_does_not_exist_yet(tmp_path):
    path = tmp_path / "nested" / "dir" / "patch.json"

    write_swing_tuning_patch_export(patch_payload=_payload(), path=path)

    assert path.parent.is_dir()
    assert path.exists()


def test_writes_json_with_trailing_newline(tmp_path):
    path = tmp_path / "patch.json"
    payload = _payload()

    write_swing_tuning_patch_export(patch_payload=payload, path=path)

    text = path.read_text()
    assert text.endswith("\n")
    assert text == json.dumps(payload, indent=2, default=str) + "\n"


def test_returned_metadata_shape_is_exact(tmp_path):
    path = tmp_path / "patch.json"
    payload = _payload(item_count=3, artifact_type="swing_tuning_patch_review")

    metadata = write_swing_tuning_patch_export(patch_payload=payload, path=path)

    assert metadata == {
        "path": str(path),
        "item_count": 3,
        "artifact_type": "swing_tuning_patch_review",
    }


def test_item_count_and_artifact_type_read_from_payload_not_recomputed(tmp_path):
    path = tmp_path / "patch.json"
    # item_count intentionally does not match len(patch_items) to prove the
    # writer trusts the payload rather than recomputing from patch_items.
    payload = _payload(
        patch_items=[{"a": 1}, {"b": 2}],
        item_count=99,
    )

    metadata = write_swing_tuning_patch_export(patch_payload=payload, path=path)

    assert metadata["item_count"] == 99
