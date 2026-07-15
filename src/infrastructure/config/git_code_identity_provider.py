"""
Read-only git code identity provider for the DQ-000 audit baseline manifest.

Never fails the manifest when git is unavailable; reports a warning instead.

Layer: Infrastructure
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.application.use_case.build_audit_baseline_manifest_use_case import AuditCodeIdentity

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_GIT_TIMEOUT_SECONDS = 5


class GitCodeIdentityProvider:
    """Reads current commit hash, dirty state, and short status via git."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or _PROJECT_ROOT
        self._warnings: list[str] = []

    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    def code_identity(self) -> AuditCodeIdentity:
        commit = self._run("git", "rev-parse", "HEAD")
        status_output = self._run("git", "status", "--short")

        if commit is None or status_output is None:
            self._warnings.append("git_unavailable")
            return AuditCodeIdentity(git_commit=None, git_dirty=False, git_status_short=())

        status_lines = tuple(
            line for line in status_output.splitlines() if line.strip()
        )
        return AuditCodeIdentity(
            git_commit=commit.strip() or None,
            git_dirty=bool(status_lines),
            git_status_short=status_lines,
        )

    def _run(self, *args: str) -> str | None:
        try:
            result = subprocess.run(
                args,
                cwd=self._project_root,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout
