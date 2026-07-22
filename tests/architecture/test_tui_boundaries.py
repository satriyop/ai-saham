"""Executable import and side-effect guards for the optional TUI adapter."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

TUI_ROOT = Path("src/adapters/tui")
TUI_COMMAND = Path("src/adapters/cli/tui_commands.py")
FORBIDDEN_ALL_IMPORTS = (
    "httpx",
    "openai",
    "playwright",
    "requests",
    "sqlite3",
    "src.adapters.cli",
    "subprocess",
    "yfinance",
    "yaml",
)
FORBIDDEN_NON_COMPOSITION_IMPORTS = (
    "src.application.rules",
    "src.application.services",
    "src.domain.services",
    "src.infrastructure",
)
FORBIDDEN_WRITE_CALLS = {
    "mkdir",
    "open",
    "rename",
    "replace",
    "rmdir",
    "system",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}
FORBIDDEN_TUI_CAPABILITY_SYMBOLS = {
    "GetSystemStatusUseCase",
    "SQLiteWatchlistRepository",
    "SaveScreenWatchlistUseCase",
    "RecordAccumulationObservationsUseCase",
    "GenerateSignalForwardLabelsUseCase",
    "BackfillSignalObservationsUseCase",
    "RepairCandidateObservationsUseCase",
    "RepairSignalForwardLabelsUseCase",
    "OpeningTuneUseCase",
    "ReportSignalReadinessUseCase",
    "ListSignalResearchScopesUseCase",
    "auto_refresh_swing_data",
    "fetch_swing_sentiment",
}
CANONICAL_ACTION_VOCABULARY = {
    "ENTER",
    "WATCH",
    "AVOID",
    "BLOCKED_EXECUTION",
    "BLOCKED_STRUCTURAL",
}


@dataclass(frozen=True)
class TuiBoundaryViolation:
    path: Path
    line: int
    detail: str


def _matches(imported: str, forbidden: str) -> bool:
    return imported == forbidden or imported.startswith(forbidden + ".")


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.lineno, node.module


def _find_tui_boundary_violations(root: Path) -> list[TuiBoundaryViolation]:
    violations: list[TuiBoundaryViolation] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        is_composition = path.name == "composition.py"
        for line, imported in _imports(tree):
            for forbidden in FORBIDDEN_ALL_IMPORTS:
                if _matches(imported, forbidden):
                    violations.append(
                        TuiBoundaryViolation(path, line, f"forbidden import {imported}")
                    )
            if not is_composition:
                for forbidden in FORBIDDEN_NON_COMPOSITION_IMPORTS:
                    if _matches(imported, forbidden):
                        violations.append(
                            TuiBoundaryViolation(
                                path,
                                line,
                                f"only composition.py may import {forbidden}",
                            )
                        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            else:
                continue
            if call_name in FORBIDDEN_WRITE_CALLS:
                violations.append(
                    TuiBoundaryViolation(path, node.lineno, f"forbidden write call {call_name}")
                )
    return violations


def test_tui_adapter_boundaries_have_no_violations():
    violations = _find_tui_boundary_violations(TUI_ROOT)

    assert not violations, "\n".join(
        f"{item.path}:{item.line}: {item.detail}" for item in violations
    )


def test_tui_boundary_guard_detects_forbidden_fixture(tmp_path):
    fixture_root = tmp_path / "src" / "adapters" / "tui"
    fixture_root.mkdir(parents=True)
    (fixture_root / "bad_screen.py").write_text(
        "from src.infrastructure.persistence.sqlite_market_repository import "
        "SQLiteMarketRepository\n",
        encoding="utf-8",
    )

    violations = _find_tui_boundary_violations(fixture_root)

    assert len(violations) == 1
    assert violations[0].detail == "only composition.py may import src.infrastructure"


def test_lazy_cli_module_has_no_top_level_tui_import():
    tree = ast.parse(TUI_COMMAND.read_text(encoding="utf-8"))
    top_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.append(node.module)

    assert not any(
        _matches(imported, "textual") or _matches(imported, "src.adapters.tui")
        for imported in top_level_imports
    )


def test_tui_does_not_compose_forbidden_provider_or_write_capabilities():
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(TUI_ROOT.rglob("*.py")))
    assert not (FORBIDDEN_TUI_CAPABILITY_SYMBOLS & set(source.split()))
    for symbol in FORBIDDEN_TUI_CAPABILITY_SYMBOLS:
        assert symbol not in source


def test_tui_has_no_removed_research_health_modules_or_route_action():
    source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(TUI_ROOT.rglob("*.py")))
    assert "research_health" not in source
    assert "show_research" not in source
    assert 'Binding("3"' not in source


def test_tui_source_defines_no_canonical_action_vocabulary():
    string_literals = set()
    for path in sorted(TUI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        string_literals.update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    assert not (CANONICAL_ACTION_VOCABULARY & string_literals)
