import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.adapters.composition.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow,
    create_accumulation_screen_workflow_bundle,
)

MODULE_PATH = "src.adapters.composition.screen_accum_workflow_factory"
SOURCE_FILE = (
    Path(__file__).resolve().parents[3]
    / "src/adapters/composition/screen_accum_workflow_factory.py"
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


def test_workflow_uses_deps_configured_signal_engine_exactly_once():
    """HIGH-2 Finding 1: the composition root must build exactly one
    configured SignalEngine per invocation via deps.create_signal_engine()
    and inject that same instance into the screen use case — never a bare
    unconfigured SignalEngine(), and never more than one engine per call."""
    deps = _make_dependencies()
    with patch(f"{MODULE_PATH}.create_accumulation_screen_use_case") as mock_use_case:
        create_accumulation_screen_workflow(
            db_path=Path("db.sqlite"),
            screener_config=MagicMock(),
            dependencies=deps,
        )

    deps.create_signal_engine.assert_called_once_with()
    assert (
        mock_use_case.call_args.kwargs["signal_engine"]
        is deps.create_signal_engine.return_value
    )


def test_workflow_bundle_uses_deps_configured_signal_engine_exactly_once():
    """Same composition-root guarantee for the observation-recording bundle
    path (create_accumulation_screen_workflow_bundle)."""
    deps = _make_dependencies()
    with patch(f"{MODULE_PATH}.create_accumulation_screen_use_case_bundle") as mock_bundle:
        create_accumulation_screen_workflow_bundle(
            db_path=Path("db.sqlite"),
            screener_config=MagicMock(),
            dependencies=deps,
        )

    deps.create_signal_engine.assert_called_once_with()
    assert (
        mock_bundle.call_args.kwargs["signal_engine"]
        is deps.create_signal_engine.return_value
    )


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
