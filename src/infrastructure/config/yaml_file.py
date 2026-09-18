"""Small YAML file reader shared by typed config loaders.

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def read_yaml_dict(path: Path) -> dict[str, Any]:
    """Parse ``path`` as YAML; missing file or non-mapping content yields ``{}``."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}
