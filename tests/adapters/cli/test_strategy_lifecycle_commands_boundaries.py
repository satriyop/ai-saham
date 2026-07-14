"""
Boundary tests for strategy_lifecycle_commands.py.

Ensures the command module stays a thin Typer adapter that only reaches
infrastructure through strategy_lifecycle_factory.py, not directly.

Layer: Adapter (test)
"""

from pathlib import Path

_MODULE_PATH = Path("src/adapters/cli/strategy_lifecycle_commands.py")

_FORBIDDEN_SYMBOLS = (
    "create_indicator_registry",
    "RulesYamlLoader",
    "SkillGeneratorService",
    "MarkdownSkillWriter",
    "AnnotationReader",
    "RulesHasher",
    "YamlStrategyDocumentReader",
)


def test_command_module_does_not_import_infrastructure_directly():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("from src.infrastructure"), (
            f"strategy_lifecycle_commands.py imports infrastructure directly: {stripped}"
        )
        assert not stripped.startswith("import src.infrastructure"), (
            f"strategy_lifecycle_commands.py imports infrastructure directly: {stripped}"
        )


def test_command_module_does_not_reference_infrastructure_symbols():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    for symbol in _FORBIDDEN_SYMBOLS:
        assert symbol not in source, (
            f"strategy_lifecycle_commands.py references infrastructure symbol: {symbol}"
        )
