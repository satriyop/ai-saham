"""
Read-only validation panel fixture reader for the DQ-000 audit baseline
manifest (config/audit_validation_panel.yaml).

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.use_case.build_audit_baseline_manifest_use_case import (
    AuditValidationScope,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PANEL_PATH = _PROJECT_ROOT / "config" / "audit_validation_panel.yaml"


class YamlAuditValidationPanelReader:
    """Loads the committed deterministic validation panel fixture."""

    def __init__(self, panel_path: Path | None = None) -> None:
        self._panel_path = panel_path or _DEFAULT_PANEL_PATH
        self._warnings: list[str] = []

    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    def validation_scope(self, tickers_override: tuple[str, ...]) -> AuditValidationScope:
        if not self._panel_path.exists():
            self._warnings.append("validation_panel_missing")
            return AuditValidationScope(tickers=tuple(tickers_override), dates=())

        data = yaml.safe_load(self._panel_path.read_text(encoding="utf-8")) or {}
        panel_tickers = tuple(str(t).upper() for t in data.get("tickers", []) or [])
        panel_dates = tuple(str(d) for d in data.get("dates", []) or [])

        tickers = tuple(t.upper() for t in tickers_override) or panel_tickers
        return AuditValidationScope(tickers=tickers, dates=panel_dates)
