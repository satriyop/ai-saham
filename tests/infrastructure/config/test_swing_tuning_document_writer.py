"""Tests for the swing tuning document read/write mechanics (infrastructure)."""

import pytest

from src.infrastructure.config.swing_tuning_document_writer import (
    read_swing_tuning_document,
    write_swing_tuning_document,
)


def test_read_swing_tuning_document_parses_mapping(tmp_path):
    path = tmp_path / "signal_engine.yaml"
    path.write_text("signal_engine:\n  classification:\n    strong_min_score: 70\n")

    document = read_swing_tuning_document(path)

    assert document == {"signal_engine": {"classification": {"strong_min_score": 70}}}


def test_read_swing_tuning_document_rejects_non_mapping(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n")

    with pytest.raises(ValueError, match="must be a mapping"):
        read_swing_tuning_document(path)


def test_write_then_read_round_trips_document(tmp_path):
    path = tmp_path / "signal_engine.yaml"
    document = {"signal_engine": {"classification": {"strong_min_score": 71}}}

    write_swing_tuning_document(path, document)

    assert read_swing_tuning_document(path) == document
