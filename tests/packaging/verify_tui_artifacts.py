"""Verify built distributions retain the optional TUI package and metadata."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

REQUIRED_TUI_FILES = (
    "src/adapters/tui/main.py",
    "src/adapters/tui/composition.py",
    "src/adapters/tui/screens/daily_screen.py",
    "src/adapters/tui/screens/candidate_browser_screen.py",
    "src/adapters/tui/screens/ticker_research_screen.py",
    "src/adapters/tui/screens/research_health_screen.py",
)


def _assert_required_files(names: list[str]) -> None:
    for required in REQUIRED_TUI_FILES:
        assert any(name.endswith(required) for name in names), required


def verify_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        _assert_required_files(names)
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
    assert "tui" in metadata.get_all("Provides-Extra", [])
    textual_requirements = [
        item for item in metadata.get_all("Requires-Dist", []) if item.lower().startswith("textual")
    ]
    assert len(textual_requirements) == 1
    assert "extra == 'tui'" in textual_requirements[0]
    assert ">=8.2" in textual_requirements[0]
    assert "<9" in textual_requirements[0]


def verify_sdist(path: Path) -> None:
    with tarfile.open(path) as archive:
        names = archive.getnames()
    _assert_required_files(names)
    assert any(name.endswith("/pyproject.toml") for name in names)


def main() -> None:
    artifact_dir = Path(sys.argv[1])
    wheels = list(artifact_dir.glob("*.whl"))
    sdists = list(artifact_dir.glob("*.tar.gz"))
    assert len(wheels) == 1, wheels
    assert len(sdists) == 1, sdists
    verify_wheel(wheels[0])
    verify_sdist(sdists[0])


if __name__ == "__main__":
    main()
