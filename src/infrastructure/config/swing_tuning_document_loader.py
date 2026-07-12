"""Document loader for swing tuning config paths.

Layer: Infrastructure
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Callable

import yaml


def load_swing_tuning_document(
    file_path: str,
    config_root: Path | str = Path("."),
) -> dict | None:
    """Load a YAML document by relative file_path under config_root.

    Returns None when the file does not exist (distinct from an existing
    but empty file, which returns {}).
    """
    yaml_path = Path(config_root) / file_path
    if not yaml_path.exists():
        return None
    with yaml_path.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh) or {}
    return document if isinstance(document, dict) else {}


def swing_tuning_document_loader(
    config_root: Path | str = Path("."),
) -> Callable[[str], dict | None]:
    """Build a document-loader callable bound to a config root."""
    return partial(load_swing_tuning_document, config_root=config_root)
