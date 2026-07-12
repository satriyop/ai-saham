"""Tests for the swing tuning document loader (infrastructure)."""

from src.infrastructure.config.swing_tuning_document_loader import (
    load_swing_tuning_document,
    swing_tuning_document_loader,
)


def test_load_swing_tuning_document_reads_existing_file(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "swing_setups.yaml").write_text(
        "setups:\n  foreign-bounce:\n    partial_max_failed_gates: 2\n",
        encoding="utf-8",
    )

    document = load_swing_tuning_document("config/swing_setups.yaml", config_root=tmp_path)

    assert document == {"setups": {"foreign-bounce": {"partial_max_failed_gates": 2}}}


def test_load_swing_tuning_document_missing_file_returns_none(tmp_path):
    document = load_swing_tuning_document("config/nonexistent.yaml", config_root=tmp_path)
    assert document is None


def test_load_swing_tuning_document_empty_file_returns_empty_dict(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "empty.yaml").write_text("", encoding="utf-8")

    document = load_swing_tuning_document("config/empty.yaml", config_root=tmp_path)

    assert document == {}


def test_swing_tuning_document_loader_binds_config_root(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "swing_setups.yaml").write_text("setups: {}\n", encoding="utf-8")

    loader = swing_tuning_document_loader(tmp_path)

    assert loader("config/swing_setups.yaml") == {"setups": {}}
    assert loader("config/nonexistent.yaml") is None
