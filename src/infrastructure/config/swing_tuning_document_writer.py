"""Read/write mechanics for swing tuning patch YAML documents.

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

import yaml


def read_swing_tuning_document(full_path: Path) -> dict:
    """Read and parse a YAML document from an absolute/resolved path."""
    with full_path.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh) or {}
    if not isinstance(document, dict):
        raise ValueError(f"YAML document must be a mapping: {full_path}")
    return document


def write_swing_tuning_document(full_path: Path, document: dict) -> None:
    """Write a YAML document back to an absolute/resolved path."""
    with full_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            document,
            fh,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )
