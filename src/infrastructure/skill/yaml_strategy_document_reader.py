"""
YAML implementation of StrategyDocumentReader.

Layer: Infrastructure
"""

from pathlib import Path
from typing import Any, Mapping

import yaml

from src.application.ports.strategy_document_reader import StrategyDocumentReader


class YamlStrategyDocumentReader(StrategyDocumentReader):
    """Reads strategy configuration from YAML files."""

    def read_strategy(self, path: Path) -> Mapping[str, Any]:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("Strategy document is not a dictionary")
        return data
