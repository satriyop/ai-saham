"""
Filesystem writer for swing tuning patch export artifacts.

Layer: Adapter
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_swing_tuning_patch_export(
    *,
    patch_payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(patch_payload, indent=2, default=str) + "\n")
    return {
        "path": str(path),
        "item_count": patch_payload["item_count"],
        "artifact_type": patch_payload["artifact_type"],
    }
