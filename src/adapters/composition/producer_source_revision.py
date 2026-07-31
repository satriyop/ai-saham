"""Stable producer provenance for learning artifacts.

Layer: Adapter. Domain requires a non-empty source_revision; this module
supplies a deterministic package identity and, when available, a git SHA for
operator traceback. Git failure is non-fatal — package version alone is valid.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

from src import __version__


@lru_cache(maxsize=1)
def resolve_producer_source_revision(*, repo_root: Path | None = None) -> str:
    """Return a non-empty revision string such as ``ai-saham@0.1.0+git:abc1234``.

    Always includes the package version. Appends short git HEAD when the
    repository is available so operators can distinguish local builds.
    """
    base = f"ai-saham@{__version__}"
    root = repo_root or Path(__file__).resolve().parents[3]
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return base
    sha = completed.stdout.strip()
    if not sha or any(c.isspace() for c in sha):
        return base
    return f"{base}+git:{sha}"
