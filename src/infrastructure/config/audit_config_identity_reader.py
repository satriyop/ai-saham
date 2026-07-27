"""
Read-only config file identity reader for the DQ-000 audit baseline manifest.

Layer: Infrastructure
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.application.use_case.build_audit_baseline_manifest_use_case import (
    AuditConfigIdentity,
    ConfigFileIdentity,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

_APP_CONFIG_RELATIVE_PATH = "config/default.yaml"
_USER_CONFIG_RELATIVE_PATH = "config/user.yaml"

_TRACKED_CONFIG_RELATIVE_PATHS = (
    "config/default.yaml",
    "config/user.yaml",
    "config/data_sources.yaml",
    "config/signal_engine.yaml",
    "config/risk_engine.yaml",
    "config/market_context_engine.yaml",
    "config/accumulation_screener.yaml",
    "config/swing_setups.yaml",
    "config/swing_targets.yaml",
    "config/audit_validation_panel.yaml",
)


class FileAuditConfigIdentityReader:
    """Hashes a fixed set of tracked config files relative to the project root."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or _PROJECT_ROOT

    def warnings(self) -> tuple[str, ...]:
        return ()

    def config_identity(self) -> AuditConfigIdentity:
        config_files = tuple(
            self._file_identity(relative_path) for relative_path in _TRACKED_CONFIG_RELATIVE_PATHS
        )
        user_config_exists = (self._project_root / _USER_CONFIG_RELATIVE_PATH).exists()
        return AuditConfigIdentity(
            app_config_path=_APP_CONFIG_RELATIVE_PATH,
            user_config_path=_USER_CONFIG_RELATIVE_PATH,
            user_config_exists=user_config_exists,
            config_files=config_files,
        )

    def _file_identity(self, relative_path: str) -> ConfigFileIdentity:
        absolute_path = self._project_root / relative_path
        if not absolute_path.exists():
            return ConfigFileIdentity(path=relative_path, exists=False, sha256=None)
        return ConfigFileIdentity(
            path=relative_path,
            exists=True,
            sha256=hashlib.sha256(absolute_path.read_bytes()).hexdigest(),
        )
