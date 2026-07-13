import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.adapters.cli.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow,
)

MODULE_PATH = "src.adapters.cli.screen_accum_workflow_factory"
SOURCE_FILE = (
    Path(__file__).resolve().parents[3]
    / "src/adapters/cli/screen_accum_workflow_factory.py"
)


def _make_dependencies():
    deps = MagicMock()
    deps.market_repository = MagicMock(name="market_repository")
    return deps


def test_with_risk_false_does_not_call_risk_factory():
    deps = _make_dependencies()
    with patch(f"{MODULE_PATH}.create_accumulation_assess_risk_use_case") as mock_risk, \
         patch(f"{MODULE_PATH}.create_accumulation_screen_use_case") as mock_use_case:
        create_accumulation_screen_workflow(
            db_path=Path("db.sqlite"),
            screener_config=MagicMock(),
            with_risk=False,
            dependencies=deps,
        )

    mock_risk.assert_not_called()
    assert mock_use_case.call_args.kwargs["risk_use_case"] is None


def test_with_risk_true_calls_risk_factory_with_market_repository():
    deps = _make_dependencies()
    with patch(f"{MODULE_PATH}.create_accumulation_assess_risk_use_case") as mock_risk, \
         patch(f"{MODULE_PATH}.create_accumulation_screen_use_case") as mock_use_case:
        create_accumulation_screen_workflow(
            db_path=Path("db.sqlite"),
            screener_config=MagicMock(),
            with_risk=True,
            dependencies=deps,
        )

    mock_risk.assert_called_once_with(market_repository=deps.market_repository)
    assert mock_use_case.call_args.kwargs["risk_use_case"] is mock_risk.return_value


def test_module_does_not_import_private_or_bootstrap_helpers():
    tree = ast.parse(SOURCE_FILE.read_text())
    imported_names = set()
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    assert "src.application.services.bootstrap" not in imported_modules
    assert "_resolve_risk_gates" not in imported_names
    assert "load_engine_config" not in imported_names
    assert "APP_CFG" not in imported_names
    assert "AssessRiskUseCase" not in imported_names
