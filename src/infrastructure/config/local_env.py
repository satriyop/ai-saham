"""Narrow reader for local, git-ignored environment-file values.

This module does not mutate ``os.environ`` and deliberately implements only
the small ``KEY=VALUE`` subset needed by local composition roots. Exported
process variables remain authoritative at the caller.

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[3]
_DEFAULT_ENV_PATH = _PROJECT_ROOT / ".env"


def read_local_env_value(name: str, *, path: Path | None = None) -> str | None:
    """Return the last non-empty ``name`` value without exporting any variables."""
    if not name or "=" in name or any(character.isspace() for character in name):
        raise ValueError("environment variable name must be a non-empty key")

    env_path = path or _DEFAULT_ENV_PATH
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None

    resolved: str | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, separator, raw_value = line.partition("=")
        if not separator or key.strip() != name:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        resolved = value or None
    return resolved
